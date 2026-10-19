/** One history read at a time. Ordinary refreshes never reset its deadline. */
export type HistorySchedulerOptions = {
  run: (signal: AbortSignal) => Promise<void>;
  onFailure: (error: unknown) => void;
  onTimeout: () => void;
  timeoutMs?: number;
  setTimer?: (callback: () => void, delay: number) => unknown;
  clearTimer?: (timer: unknown) => void;
};
export class ResearchHistoryScheduler {
  private active: { abort: AbortController; timer: unknown } | null = null;
  private requested = false;
  private paused = false;
  private disposed = false;
  private readonly setTimer: NonNullable<HistorySchedulerOptions["setTimer"]>;
  private readonly clearTimer: NonNullable<HistorySchedulerOptions["clearTimer"]>;
  private readonly options: HistorySchedulerOptions;
  constructor(options: HistorySchedulerOptions) {
    this.options = options;
    this.setTimer = options.setTimer ?? ((callback, delay) => setTimeout(callback, delay));
    this.clearTimer = options.clearTimer ?? (timer => clearTimeout(timer as ReturnType<typeof setTimeout>));
    if (!Number.isSafeInteger(options.timeoutMs ?? 15000) || (options.timeoutMs ?? 15000) < 1) throw new RangeError("Invalid history deadline");
  }
  request(): void { if (!this.disposed) { this.requested = true; this.start(); } }
  /** Mutation reads cannot publish over its result; retain one refresh for afterward. */
  pause(): void { if (!this.disposed) { this.paused = true; this.requested = true; this.active?.abort.abort(); } }
  resume(): void { if (!this.disposed) { this.paused = false; this.start(); } }
  /** Selection, access and unmount changes cancel immediately and never resume this job. */
  dispose(): void {
    this.disposed = true; this.requested = false;
    if (this.active) { this.active.abort.abort(); this.clearTimer(this.active.timer); }
  }
  private start(): void {
    if (this.disposed || this.paused || this.active || !this.requested) return;
    this.requested = false;
    const current = { abort: new AbortController(), timer: undefined as unknown };
    this.active = current;
    current.timer = this.setTimer(() => {
      if (!this.disposed && this.active === current && !current.abort.signal.aborted) { current.abort.abort(); this.options.onTimeout(); }
    }, this.options.timeoutMs ?? 15000);
    void Promise.resolve().then(async () => {
      if (current.abort.signal.aborted) return;
      try { await this.options.run(current.abort.signal); }
      catch (error) { if (!this.disposed && !current.abort.signal.aborted) this.options.onFailure(error); }
    }).finally(() => {
      this.clearTimer(current.timer);
      if (this.active === current) this.active = null;
      this.start();
    });
  }
}
