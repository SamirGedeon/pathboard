export interface Task {
  id: string;
  title: string;
  hours: number;
  dependencies: string[];
}
export interface PlannedTask extends Task {
  start: number;
  finish: number;
  slack: number;
  critical: boolean;
}
export interface Plan {
  duration: number;
  effort: number;
  critical_count: number;
  tasks: PlannedTask[];
}
export interface Project {
  id: string;
  name: string;
  description: string;
  tasks: Task[];
  version: number;
  updated: number;
  plan: Plan;
}
export interface Simulation {
  baseline: number;
  impact: number;
  plan: Plan;
  version: number;
}
