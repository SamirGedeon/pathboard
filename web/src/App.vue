<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Project, Task, Simulation } from "./types";
const user = ref<{ email: string } | null>(null),
  signup = ref(true),
  busy = ref(false),
  error = ref(""),
  notice = ref("");
const projects = ref<Project[]>([]),
  selected = ref<Project | null>(null),
  creating = ref(false),
  taskForm = ref(false),
  editing = ref<string | null>(null),
  search = ref("");
const name = ref(""),
  description = ref(""),
  title = ref(""),
  hours = ref(4),
  dependencies = ref<string[]>([]),
  subject = ref(""),
  simHours = ref(8),
  simulation = ref<Simulation | null>(null);
const filtered = computed(() =>
  projects.value.filter((p) =>
    p.name.toLowerCase().includes(search.value.toLowerCase()),
  ),
);
const totalTasks = computed(() =>
  projects.value.reduce((n, p) => n + p.tasks.length, 0),
);
const criticalTasks = computed(() =>
  projects.value.reduce((n, p) => n + p.plan.critical_count, 0),
);
async function api(path: string, body?: unknown, method?: string) {
  const response = await fetch("/api" + path, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) user.value = null;
    throw new Error(
      typeof data.detail === "string" ? data.detail : "Request failed.",
    );
  }
  return data;
}
async function task(fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
function toast(text: string) {
  notice.value = text;
  setTimeout(() => (notice.value = ""), 3000);
}
async function refresh() {
  projects.value = await api("/projects");
}
onMounted(() => {
  api("/me")
    .then(async (u) => {
      user.value = u;
      await refresh();
    })
    .catch(() => {});
});
function auth(event: Event) {
  const data = Object.fromEntries(
    new FormData(event.target as HTMLFormElement),
  );
  task(async () => {
    user.value = await api(
      "/auth/" + (signup.value ? "signup" : "login"),
      data,
    );
    await refresh();
  });
}
function home() {
  selected.value = null;
  creating.value = false;
  taskForm.value = false;
  simulation.value = null;
  task(refresh);
}
function open(project: Project) {
  task(async () => {
    selected.value = await api("/projects/" + project.id);
    taskForm.value = false;
    simulation.value = null;
    subject.value = selected.value!.tasks[0]?.id || "";
  });
}
function beginProject() {
  name.value = "";
  description.value = "";
  creating.value = true;
}
function createProject() {
  task(async () => {
    selected.value = await api("/projects", {
      name: name.value,
      description: description.value,
      tasks: [],
    });
    creating.value = false;
    await refresh();
    toast("Project created. Add your first task.");
  });
}
function beginTask(taskToEdit?: Task) {
  editing.value = taskToEdit?.id || null;
  title.value = taskToEdit?.title || "";
  hours.value = taskToEdit?.hours || 4;
  dependencies.value = [...(taskToEdit?.dependencies || [])];
  taskForm.value = true;
  simulation.value = null;
}
async function saveTasks(tasks: Task[]) {
  const p = selected.value!;
  selected.value = await api(
    "/projects/" + p.id,
    { name: p.name, description: p.description, tasks, version: p.version },
    "PUT",
  );
  await refresh();
  simulation.value = null;
  subject.value =
    selected.value!.tasks.find((t) => t.id === subject.value)?.id ||
    selected.value!.tasks[0]?.id ||
    "";
}
function saveTask() {
  task(async () => {
    const newTask: Task = {
      id: editing.value || crypto.randomUUID(),
      title: title.value,
      hours: hours.value,
      dependencies: dependencies.value,
    };
    const tasks = selected.value!.tasks.filter((t) => t.id !== editing.value);
    tasks.push(newTask);
    await saveTasks(tasks);
    taskForm.value = false;
    toast("Task saved. The plan has been recalculated.");
  });
}
function removeTask(id: string) {
  task(async () => {
    const p = selected.value!;
    if (p.tasks.some((t) => t.dependencies.includes(id)))
      throw new Error(
        "Remove this task from other tasks’ prerequisites first.",
      );
    await saveTasks(p.tasks.filter((t) => t.id !== id));
    taskForm.value = false;
    toast("Task removed.");
  });
}
function simulate() {
  task(async () => {
    const p = selected.value!;
    simulation.value = await api("/projects/" + p.id + "/simulate", {
      task_id: subject.value,
      hours: simHours.value,
      version: p.version,
    });
  });
}
function logout() {
  task(async () => {
    await api("/logout", {});
    user.value = null;
    selected.value = null;
    projects.value = [];
    creating.value = false;
  });
}
const taskName = (id: string) =>
  selected.value?.tasks.find((t) => t.id === id)?.title || id;
const max = Math.max;
</script>

<template>
  <main v-if="!user" class="entry">
    <section class="pitch">
      <a class="brand" href="/"
        ><span class="logo"><i></i><i></i><i></i></span>Pathboard</a
      >
      <div class="eyebrow">LESS GUESSWORK. A CLEARER PATH.</div>
      <h1>See what shapes<br /><em>your deadline.</em></h1>
      <p>
        Connect your tasks. Find the work that matters most. Explore the impact
        of a change before you commit to it.
      </p>
      <div class="preview">
        <div class="preview-head">
          <span>YOUR NEXT PROJECT</span><b>32 h</b>
        </div>
        <div class="preview-line">
          <span>Discover</span><i style="width: 25%; margin-left: 0"></i>
        </div>
        <div class="preview-line">
          <span>Design</span><i style="width: 40%; margin-left: 25%"></i>
        </div>
        <div class="preview-line">
          <span>Build</span><i style="width: 35%; margin-left: 65%"></i>
        </div>
        <div class="preview-foot">
          <span class="dot"></span> Every task has its place.
        </div>
      </div>
      <div class="pitch-tags">
        <span>Dependency planning</span><span>Critical path analysis</span>
      </div>
    </section>
    <section class="panel auth">
      <span class="eyebrow">YOUR PERSONAL PLANNING SPACE</span>
      <h2>
        {{ signup ? "Plan with a little more clarity." : "Welcome back." }}
      </h2>
      <p>
        {{
          signup
            ? "Create an account to start connecting the dots."
            : "Your next clear step is waiting."
        }}
      </p>
      <form @submit.prevent="auth">
        <label
          >Email<input
            name="email"
            type="email"
            autocomplete="email"
            required
            placeholder="you@example.com" /></label
        ><label
          >Password<input
            name="password"
            type="password"
            :autocomplete="signup ? 'new-password' : 'current-password'"
            minlength="10"
            maxlength="128"
            required
            placeholder="At least 10 characters" /></label
        ><button class="primary wide" :disabled="busy">
          {{ busy ? "Please wait…" : signup ? "Create account" : "Sign in" }}
        </button>
      </form>
      <button class="text auth-toggle" @click="signup = !signup">
        {{
          signup
            ? "Already have an account? Sign in"
            : "New here? Create an account"
        }}
      </button>
      <p class="fine">
        Private projects. Transparent calculations.<br />No external services
        required.
      </p>
    </section>
  </main>
  <div v-else class="layout">
    <aside>
      <a class="brand" href="/"
        ><span class="logo"><i></i><i></i><i></i></span>Pathboard</a
      >
      <div class="workspace-tag">
        <span class="avatar">P</span>
        <div>Personal workspace<small>A PLACE TO THINK AHEAD</small></div>
      </div>
      <div class="nav-caption">WORKSPACE</div>
      <button class="nav active" @click="home">
        <span class="grid-icon">▦</span> My projects
        <b>{{ projects.length }}</b>
      </button>
      <div class="aside-tip">
        <div class="tip-lines"><i></i><i></i><i></i></div>
        <strong>Find your next clear step.</strong>
        <p>A good plan makes the connections visible.</p>
      </div>
      <div class="profile">
        <span class="avatar">{{ user.email[0].toUpperCase() }}</span>
        <div>
          <span>{{ user.email }}</span
          ><button class="text" @click="logout">Sign out</button>
        </div>
      </div>
    </aside>
    <main class="workspace">
      <header>
        <span
          >PERSONAL WORKSPACE <b>/</b>
          {{ selected ? selected.name : "PROJECT OVERVIEW" }}</span
        ><span class="header-pill"
          ><i></i> A little clarity goes a long way</span
        >
      </header>
      <template v-if="!selected"
        ><section class="page-heading">
          <div>
            <div class="eyebrow">MAKE THE CONNECTIONS</div>
            <h1>
              A clearer view of<br class="mobile-break" />
              what’s ahead.
            </h1>
            <p>Turn a list of tasks into a plan that makes sense.</p>
          </div>
          <button class="primary" @click="beginProject">+ New project</button>
        </section>
        <section class="metrics">
          <div>
            <span>YOUR PROJECTS</span
            ><strong
              >{{ projects.length }}<small>ideas taking shape</small></strong
            ><i class="metric-icon peach">▦</i>
          </div>
          <div>
            <span>PLANNED TASKS</span
            ><strong
              >{{ totalTasks
              }}<small>pieces of the bigger picture</small></strong
            ><i class="metric-icon lavender">≡</i>
          </div>
          <div>
            <span>CRITICAL TASKS</span
            ><strong
              >{{ criticalTasks
              }}<small>directly shaping the deadline</small></strong
            ><i class="metric-icon mint">⌁</i>
          </div>
        </section>
        <form
          v-if="creating"
          class="panel project-form"
          @submit.prevent="createProject"
        >
          <h2>A new project, a clearer path.</h2>
          <label
            >Project name<input
              v-model="name"
              required
              maxlength="80"
              placeholder="e.g. Website launch" /></label
          ><label
            >Description<textarea
              v-model="description"
              maxlength="400"
              placeholder="What are you working toward?"
            ></textarea>
          </label>
          <div class="form-actions">
            <button class="text" type="button" @click="creating = false">
              Cancel</button
            ><button class="primary" :disabled="busy">Create project</button>
          </div>
        </form>
        <section class="section-heading">
          <h2>
            Your projects <span>{{ projects.length }}</span>
          </h2>
          <input
            v-if="projects.length"
            v-model="search"
            aria-label="Search projects"
            placeholder="Find a project…"
          />
        </section>
        <section class="project-grid">
          <button
            v-for="p in filtered"
            :key="p.id"
            class="project-card panel"
            @click="open(p)"
          >
            <div class="card-top">
              <span class="project-icon">▤</span
              ><span class="small-tag">{{ p.tasks.length }} tasks</span>
            </div>
            <h3>{{ p.name }}</h3>
            <p>{{ p.description || "A new plan, ready to take shape." }}</p>
            <div class="mini-timeline">
              <i
                v-for="t in p.plan.tasks.slice(0, 4)"
                :key="t.id"
                :class="{ critical: t.critical }"
                :style="{
                  width:
                    max(5, (t.hours / max(1, p.plan.duration)) * 100) + '%',
                  marginLeft: (t.start / max(1, p.plan.duration)) * 100 + '%',
                }"
              ></i
              ><i v-if="!p.tasks.length" class="placeholder-bar"></i>
            </div>
            <div class="card-bottom">
              <span
                ><strong>{{ p.plan.duration }} h</strong> planned duration</span
              ><b>→</b>
            </div>
          </button>
          <div v-if="!filtered.length" class="panel empty">
            <span class="empty-icon">+</span>
            <h3>
              {{
                search
                  ? "No matching projects."
                  : "Start with the bigger picture."
              }}
            </h3>
            <p>
              {{
                search
                  ? "Try another project name."
                  : "Create a project, add a few tasks, and connect what needs to happen first."
              }}
            </p>
          </div>
        </section>
        <section class="guide">
          <span class="guide-mark">01</span>
          <div>
            <h3>Some tasks have more influence than others.</h3>
            <p>
              The critical path shows the chain of work that sets your project’s
              shortest possible duration.
            </p>
          </div>
          <span class="guide-badge">CONNECT THE DOTS</span>
        </section></template
      >
      <template v-else
        ><button class="text back" @click="home">← All projects</button>
        <section class="detail-heading">
          <div>
            <div class="eyebrow">THE BIGGER PICTURE</div>
            <h1>{{ selected.name }}</h1>
            <p>
              {{
                selected.description ||
                "Connect tasks and see your plan take shape."
              }}
            </p>
          </div>
          <button class="secondary" :disabled="busy" @click="open(selected)">
            Reload latest
          </button>
        </section>
        <section class="metrics detail-metrics">
          <div>
            <span>PLANNED DURATION</span
            ><strong
              >{{ selected.plan.duration }}<small>work hours</small></strong
            >
          </div>
          <div>
            <span>TOTAL EFFORT</span
            ><strong
              >{{ selected.plan.effort
              }}<small>task hours combined</small></strong
            >
          </div>
          <div>
            <span>CRITICAL TASKS</span
            ><strong
              >{{ selected.plan.critical_count
              }}<small>with zero scheduling slack</small></strong
            >
          </div>
        </section>
        <div class="detail-grid">
          <section class="main-column">
            <section class="panel timeline">
              <div class="panel-heading">
                <div>
                  <h2>Your project timeline</h2>
                  <p>Parallel work · no resource limits</p>
                </div>
                <span class="legend"><i></i> Critical task</span>
              </div>
              <div v-if="selected.tasks.length" class="timeline-chart">
                <div class="timeline-axis">
                  <span>TASK</span>
                  <div>
                    <span>0 h</span><span>{{ selected.plan.duration }} h</span>
                  </div>
                </div>
                <div
                  v-for="t in selected.plan.tasks"
                  :key="t.id"
                  class="timeline-row"
                >
                  <span :title="t.title">{{ t.title }}</span>
                  <div class="track">
                    <div
                      class="timeline-bar"
                      :class="{ critical: t.critical }"
                      :style="{
                        marginLeft:
                          (t.start / max(1, selected.plan.duration)) * 100 +
                          '%',
                        width:
                          (t.hours / max(1, selected.plan.duration)) * 100 +
                          '%',
                      }"
                      :aria-label="`${t.title}: hours ${t.start} to ${t.finish}`"
                    >
                      <span>{{ t.hours }} h</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="empty">
                <h3>Every plan starts with one task.</h3>
                <p>Add the first piece of work to see your timeline.</p>
              </div>
            </section>
            <section class="section-heading tasks-heading">
              <h2>
                Tasks <span>{{ selected.tasks.length }}</span>
              </h2>
              <button
                class="primary"
                :disabled="busy || selected.tasks.length >= 60"
                @click="beginTask()"
              >
                + Add task
              </button>
            </section>
            <form
              v-if="taskForm"
              class="panel task-form"
              @submit.prevent="saveTask"
            >
              <h2>{{ editing ? "Edit task" : "A new piece of the plan" }}</h2>
              <div class="task-inputs">
                <label
                  >Task title<input
                    v-model="title"
                    required
                    maxlength="80"
                    placeholder="e.g. Design the landing page" /></label
                ><label
                  >Estimate (hours)<input
                    v-model.number="hours"
                    type="number"
                    min="1"
                    max="160"
                    step="1"
                    required
                /></label>
              </div>
              <fieldset>
                <legend>
                  Prerequisites <span>What needs to finish first?</span>
                </legend>
                <label
                  v-for="t in selected.tasks.filter((t) => t.id !== editing)"
                  :key="t.id"
                  class="dependency-option"
                  ><input
                    v-model="dependencies"
                    type="checkbox"
                    :value="t.id"
                  />{{ t.title }}</label
                >
                <p
                  v-if="!selected.tasks.filter((t) => t.id !== editing).length"
                  class="hint"
                >
                  No other tasks yet. This one can start right away.
                </p>
              </fieldset>
              <div class="form-actions">
                <button type="button" class="text" @click="taskForm = false">
                  Cancel</button
                ><button class="primary" :disabled="busy">Save task</button>
              </div>
            </form>
            <div class="task-list">
              <article
                v-for="t in selected.plan.tasks"
                :key="t.id"
                class="panel task-row"
              >
                <div class="task-main">
                  <span
                    class="task-dot"
                    :class="{ critical: t.critical }"
                  ></span>
                  <div>
                    <h3>{{ t.title }}</h3>
                    <p>
                      {{
                        t.dependencies.length
                          ? "After " + t.dependencies.map(taskName).join(", ")
                          : "Ready to start"
                      }}<span> · {{ t.hours }} h</span>
                    </p>
                  </div>
                </div>
                <div class="task-actions">
                  <span class="slack" :class="{ critical: t.critical }">{{
                    t.critical ? "Critical" : t.slack + " h slack"
                  }}</span
                  ><button
                    class="text"
                    :aria-label="'Edit ' + t.title"
                    @click="beginTask(t)"
                  >
                    Edit</button
                  ><button
                    class="delete"
                    :aria-label="'Remove ' + t.title"
                    :disabled="busy"
                    @click="removeTask(t.id)"
                  >
                    ×
                  </button>
                </div>
              </article>
            </div>
          </section>
          <div class="side-column">
            <section class="panel simulator">
              <span class="eyebrow">EXPLORE BEFORE YOU COMMIT</span>
              <h2>What if things change?</h2>
              <p>
                Try a different estimate and see how it affects the deadline.
              </p>
              <form v-if="selected.tasks.length" @submit.prevent="simulate">
                <label
                  >Task to simulate<select
                    v-model="subject"
                    required
                    @change="simulation = null"
                  >
                    <option
                      v-for="t in selected.tasks"
                      :key="t.id"
                      :value="t.id"
                    >
                      {{ t.title }}
                    </option>
                  </select></label
                ><label
                  >New estimate (hours)<input
                    v-model.number="simHours"
                    type="number"
                    min="1"
                    max="160"
                    step="1"
                    required
                    @input="simulation = null" /></label
                ><button class="secondary wide" :disabled="busy">
                  Simulate impact
                </button>
              </form>
              <p v-else class="hint">Add a task to explore its impact.</p>
              <div v-if="simulation" class="simulation-result" role="status">
                <span>SIMULATED DURATION</span
                ><strong
                  >{{ simulation.plan.duration }} <small>hours</small></strong
                >
                <div :class="{ delayed: simulation.impact > 0 }">
                  {{ simulation.impact > 0 ? "+" : ""
                  }}{{ simulation.impact }} h
                  {{
                    simulation.impact > 0
                      ? "longer"
                      : simulation.impact < 0
                        ? "shorter"
                        : "change to the deadline"
                  }}
                </div>
                <p>
                  {{
                    simulation.impact === 0
                      ? "This estimate leaves the overall project duration unchanged."
                      : "This estimate changes the shortest possible project duration."
                  }}
                </p>
              </div>
              <p class="fine">A simulation never changes your saved plan.</p>
            </section>
            <section class="explanation">
              <div class="explain-icon">i</div>
              <h3>How to read your plan</h3>
              <p>
                <b>Critical tasks</b> have no slack. Increasing their estimate
                increases the project duration.
              </p>
              <p>
                <b>Slack</b> is how much a task can shift before it affects the
                deadline.
              </p>
              <p>
                Estimates use work hours, with unlimited parallel work. Team
                availability and calendars are not included.
              </p>
            </section>
            <span class="version-note"
              >Saved plan · revision {{ selected.version }}</span
            >
          </div>
        </div></template
      >
      <footer class="page-footer">
        <span>A thoughtful plan makes room for better decisions.</span
        ><span>Pathboard / 01</span>
      </footer>
    </main>
  </div>
  <div v-if="error" class="toast error" role="alert">
    {{ error }}<button aria-label="Dismiss error" @click="error = ''">×</button>
  </div>
  <div v-if="notice" class="toast" role="status">{{ notice }}</div>
</template>
