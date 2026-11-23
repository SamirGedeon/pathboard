import { test, expect } from "@playwright/test";
const password = "a-strong-browser-password";
async function register(request: any) {
  const r = await request.post("/api/auth/signup", {
    data: {
      email: "learner." + crypto.randomUUID().slice(0, 8) + "@example.com",
      password,
    },
  });
  expect(r.ok()).toBeTruthy();
}
const tasks = [
  { id: "a", title: "Discovery & research", hours: 4, dependencies: [] },
  { id: "b", title: "Interface design", hours: 6, dependencies: ["a"] },
  { id: "c", title: "Content preparation", hours: 2, dependencies: ["a"] },
  { id: "d", title: "Build & launch", hours: 8, dependencies: ["b", "c"] },
];
test("create project, connect tasks, simulate, reject cycle and preserve saved plan", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByLabel("Email", { exact: true })
    .fill("test." + crypto.randomUUID().slice(0, 8) + "@example.com");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.getByRole("button", { name: "+ New project" }).click();
  await page.getByLabel("Project name").fill("Website launch");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page.getByRole("button", { name: "+ Add task" }).click();
  await page.getByLabel("Task title").fill("Discovery");
  await page.getByLabel("Estimate (hours)", { exact: true }).fill("4");
  await page.getByRole("button", { name: "Save task" }).click();
  await expect(page.locator(".task-row")).toHaveCount(1);
  await page.getByRole("button", { name: "+ Add task" }).click();
  await page.getByLabel("Task title").fill("Build");
  await page.getByLabel("Estimate (hours)", { exact: true }).fill("6");
  await page.getByLabel("Discovery", { exact: true }).check();
  await page.getByRole("button", { name: "Save task" }).click();
  await expect(page.locator(".detail-metrics>div").first()).toContainText("10");
  await page
    .getByLabel("Task to simulate")
    .selectOption({ label: "Discovery" });
  await page.getByLabel("New estimate (hours)").fill("8");
  await page.getByRole("button", { name: "Simulate impact" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "SIMULATED DURATION" }),
  ).toContainText("14");
  await expect(page.locator(".detail-metrics>div").first()).toContainText("10");
  await page
    .getByRole("button", { name: "Edit Discovery", exact: true })
    .click();
  await page.getByLabel("Build", { exact: true }).check();
  await page.getByRole("button", { name: "Save task" }).click();
  await expect(page.getByRole("alert")).toContainText("cycle");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: "Reload latest" }).click();
  await expect(page.locator(".detail-metrics>div").first()).toContainText("10");
  await page.reload();
  await page.getByRole("button", { name: /Website launch/ }).click();
  await expect(page.locator(".task-row")).toHaveCount(2);
  expect(errors).toEqual([]);
  await page
    .getByRole("button", { name: "Remove Discovery", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("prerequisites");
  await page.getByRole("button", { name: "Remove Build", exact: true }).click();
  await expect(page.locator(".task-row")).toHaveCount(1);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Create account", exact: true }),
  ).toBeVisible();
});
test("HTTP ownership and stale revisions are enforced", async ({
  request,
  playwright,
}) => {
  await register(request);
  const p = await (
    await request.post("/api/projects", { data: { name: "Launch", tasks } })
  ).json();
  const body = {
    name: p.name,
    description: p.description,
    tasks: p.tasks,
    version: p.version,
  };
  expect(
    (await request.put("/api/projects/" + p.id, { data: body })).status(),
  ).toBe(200);
  expect(
    (await request.put("/api/projects/" + p.id, { data: body })).status(),
  ).toBe(409);
  const other = await playwright.request.newContext({
    baseURL: "http://localhost:5180",
  });
  await register(other);
  expect((await other.get("/api/projects/" + p.id)).status()).toBe(404);
  expect(
    (
      await other.post("/api/projects/" + p.id + "/simulate", {
        data: { task_id: "a", hours: 8, version: 2 },
      })
    ).status(),
  ).toBe(404);
  await other.dispose();
});
test("desktop and mobile planning workspace screenshots", async ({ page }) => {
  await register(page.request);
  for (const [name, description, graph] of [
    [
      "Website launch",
      "A focused path from first idea to a thoughtful launch.",
      tasks,
    ],
    [
      "Product onboarding",
      "Help new users find their first small win.",
      tasks.slice(0, 3),
    ],
    [
      "Brand refresh",
      "Bring a little more clarity to the way we show up.",
      tasks.slice(0, 2),
    ],
  ] as const)
    expect(
      (
        await page.request.post("/api/projects", {
          data: { name, description, tasks: graph },
        })
      ).ok(),
    ).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /A clearer view/ }),
  ).toBeVisible();
  await page.screenshot({ path: "../docs/dashboard.png", fullPage: true });
  await page.getByRole("button", { name: /Website launch/ }).click();
  await page.getByLabel("Task to simulate").selectOption("c");
  await page.getByLabel("New estimate (hours)").fill("10");
  await page.getByRole("button", { name: "Simulate impact" }).click();
  await expect(page.locator(".simulation-result")).toBeVisible();
  await page.screenshot({ path: "../docs/planner.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "../docs/mobile.png", fullPage: true });
  await page.getByRole("button", { name: "← All projects" }).click();
  await page.getByLabel("Search projects").fill("onboarding");
  await expect(page.locator(".project-card")).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
