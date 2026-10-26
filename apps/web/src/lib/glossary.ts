/** Plain-words explanations for GPUWatch's vocabulary, shown as inline hints. */
export const GLOSSARY = {
  utilization:
    "Share of time in the last sample period the GPU was running at least one kernel (NVML). 100% means always busy, not necessarily fully used.",
  idleCost:
    "What GPU time cost while nothing ran on it, at your configured rate. An idle cloud GPU costs the same as a busy one.",
  heldIdle:
    "GPU time a workload held (processes, memory: a model loaded) while utilization stayed under the idle threshold.",
  waste:
    "Estimated cost of the open findings over 30 days, from your own rates. An estimate, not a promised saving.",
  attribution:
    "Each sample's time is split across the processes on the GPU by their SM share, else their memory, else equally. Time with nothing running is idle.",
  unattributed:
    "The GPU was busy but the driver lists no processes (some containers and vGPUs hide them). Run the agent with --pid=host to fix it.",
  notAvailable:
    "The driver does not report this metric on this GPU (fan speed on passively cooled cards, ECC on consumer cards). Not the same as zero.",
  throttle:
    "The driver's clocks event reasons: why the GPU runs below full clocks. Power cap and thermal limits slow work down.",
  rate: "Hourly cost of a GPU. The most specific rate wins: a GPU's own, then its host's, then its model's.",
  ttft: "Time to first token: from request arrival to the first generated token, from the server's own histogram.",
  costPerMillion:
    "The bound GPUs' cost over the window divided by the tokens the server processed (prompt plus generated), times one million.",
  enrolment:
    "A one-time secret an agent exchanges for its own host token. One enrolment token can enrol a whole fleet until it expires or reaches its use limit.",
  simulated:
    "A demo host: the real agent with its simulated collector, sending through the same ingest API. Real hosts never show this badge.",
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
