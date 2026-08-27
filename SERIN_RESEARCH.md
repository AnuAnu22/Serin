# Serin Vision Research — Standing on the Shoulders of Giants

> Working research compendium for the Serin project. Compiled 2026-08-26 from deep
> web search over the agent-memory, autonomy, collapse, theory-of-mind, persona,
> social-companion, and small-model literature. Every claim below is cited inline
> with a source URL. Purpose: accelerate Serin by reusing what researchers and
> engineers have already proven, and to de-risk the autonomous "heart" before
> thousands of hours are spent building the wrong organ.

---

## 0. Why this file exists (the problem framing)

Serin's doctrine (`docs/SERIN_VISION.md`) is **causality, not performance**:
behavior must be *caused by* persistent accumulated state, never a fresh
die-roll. The built half is social *cognition* (perceive → understand →
believe → feel → remember). The missing half is social *agency* — a native
autonomous "heart" that lets Serin speak/act without being messaged first, and
the wider body of organs (episodic memory, theory of mind, immune/validation
gates, actuators) around it.

Two risks dominate the missing half:
1. **Model collapse** if the loop ingests its own outputs as truth (a real,
   universal failure mode — not a model-size quirk).
2. **Value/goal drift & reward hacking** over long horizons if the autonomous
   core is unconstrained.

The research below shows both are *solvable by architecture*, and that a small
model can safely occupy the "soul" slot if the body (autonomic organs) does the
critical work. This validates the **body/soul organ model** discussed in
session: the LLM is the soul (voluntary surface only), the organism is the
autonomic body.

---

## 1. Memory is the differentiator — and it is a write–manage–read loop

**Source: "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and
Emerging Frontiers" (arXiv:2603.07670, 2026 survey).**
https://arxiv.org/html/2603.07670v1

Key findings:
- Memory transforms a stateless LLM into a *self-evolving* agent: it (i)
  accumulates factual knowledge + user preferences, (ii) develops behavioral
  patterns grounded in experience, (iii) avoids repeating costly mistakes, (iv)
  continuously improves through interaction.
- The agent loop is formalized as a **write–manage–read loop inside a
  POMDP-style cycle**. Decomposition matters: separate *what is written*,
  *how it is curated/consolidated*, and *how it is retrieved*.
- Survey names the design tensions explicitly: recency vs. importance vs.
  relevance retrieval; forgetting vs. retention; capacity limits.
- 2025–2026 additions: *Agentic Memory* (learned memory control), MemBench,
  MemoryAgentBench, MemoryArena — richer eval tied to downstream agent utility.

**Mapping to Serin:** Serin already has the *write* (MemoryWriteStage, always
runs) and *read* (Qdrant/BM25 retrieval) halves, but the **manage** half
(consolidation, decay, dedup, quality curation) is partly ad hoc. The survey's
three-phase formalization is exactly the gap the `run_maintenance` pass should
own. Recommend: make `run_maintenance` the canonical *manage* stage with
explicit consolidation/decay/prune sub-phases, mirroring this taxonomy.

**Source: "A Survey on the Security of Long-Term Memory in LLM Agents: Toward
Mnemonic Sovereignty" (arXiv:2604.16548, 2026).**
https://arxiv.org/html/2604.16548v1
- Introduces **Write-Path Compromise** as a first-class threat: agents that let
  untrusted input write memory are persistently poisonable.
- Mnemonic sovereignty = the user/agent must *own and govern* what enters
  long-term memory; external inputs are quarantined before promotion to belief.

**Mapping to Serin:** This is the **immune-system organ** in the body/soul
model. Every state mutation (beliefs, goals, memories) must pass through a
provenance/validation gate before it lands in durable store. Serin's
`goals.origin_provenance` idea is the right instinct — extend it to *all*
writes. The LLM (soul) proposes; the gate (immune system) admits or rejects.

---

## 2. The believable-autonomy blueprint already exists (Generative Agents)

**Source: Park et al., "Generative Agents: Interactive Simulacra of Human
Behavior" (arXiv:2304.03442, Stanford, 2023).**
https://arxiv.org/abs/2304.03442
- 25 agents in a sandbox that *wake up, form opinions, plan days, and initiate
  conversations* entirely from an **observation → reflection → planning** loop.
- Architecture: store complete experience as natural-language memory;
  *synthesize* into higher-level **reflections**; *retrieve dynamically* to plan
  behavior. Reflection and planning feed back into the memory stream.
- Ablations showed disabling any of the three memory types (observation,
  reflection, planning) degraded believability — all three are necessary.

**Mapping to Serin:** This is the proof that the "dream-state loop" the user
intuited — the *whole cognitive subgraph running without external prompt* — is
valid and produces believable autonomous behavior. Serin already has
observation (ingest/perceive) and partial planning (ResponsePlanner). It lacks
an explicit **reflection** pass ( periodic synthesis of lower memories into
higher abstractions) — that is a missing organ. Recommend a `reflect` stage in
`run_maintenance`.

---

## 3. Model collapse is real, universal, and avoidable by grounding

**Source: Shumailov et al., "The Curse of Recursion: Training on Generated
Data Makes Models Forget" (arXiv:2305.17493 → Nature 2024, "AI models collapse
when trained on recursively generated data").**
https://arxiv.org/abs/2305.17493  ·  https://www.nature.com/articles/s41586-024-07566-y
- Recursively training a generative model on its *own* outputs causes
  irreversible **model collapse**: tails of the original distribution disappear,
  diversity is lost. Shown for VAEs, GMMs, and LLMs.
- Theorized as universal among generative models that self-train.

**Mitigation source: "Fending Off Recursive Training Induced Failure for AI
Model Collapse" (arXiv:2509.08972, 2025) and industry guidance (2025–2026).**
https://arxiv.org/pdf/2509.08972
- The fix is **not** avoiding synthetic data; it is *accumulating real
  (observed) data alongside it* and regulating the recursion.
- "Model collapse occurs if the relationship between model performance and
  training data is not grounded in real signal." (Position paper, OpenReview:
  https://openreview.net/pdf?id=ygfzWIGDN8)

**Mapping to Serin (CRITICAL — the anti-collapse rule):**
The collapse threat translates directly to the autonomous loop. If Serin's own
generated text/memories/beliefs re-enter as *undifferentiated truth*, the state
distribution collapses onto a narrow self-reinforcing attractor — and a 12B
model has less headroom to notice the drift, so it collapses *faster*.
**The architectural rule (the "heart valve"):** the loop must pump
*observed blood* — genuine external signal (real human messages, real tool
returns) — and **never let its own outputs re-enter as truth.** Every
self-generated item is a *hypothesis* (quarantined, provenance-tagged), not
fact. This is exactly the Write-Path Compromise defense (§1). Building this
valve at the *pacemaker* (before the LLM is even called) prevents paying
inference to generate collapse.

---

## 4. Self-evolution is powerful but drifts — needs continuous monitoring

**Source: "A Survey of Self-Evolving Agents: What, When, How, and Where to
Evolve" (arXiv:2507.21046, 2025/2026).**
https://arxiv.org/abs/2507.21046
- Self-evolving agents improve via experience (memory evolution, prompt
  optimization, tool/behavior learning).
- **Explicit warning:** "Continuous monitoring of agent behavior is necessary to
  detect long-horizon value drift. This can be achieved through red-teaming
  scenarios." Long-horizon self-evolution may degrade alignment/safety.
- Notes "Uncontrolled Behavior Drift" as an open problem: how to keep goals and
  values aligned with human intent as the agent evolves autonomously.

**Mapping to Serin:** This is the strongest academic backing for the user's
fear that autonomy "corrupts everything." The answer the survey gives is
*monitoring + red-teaming + bounded evolution*, not disabling autonomy. Maps to
Serin's planned panel telemetry for every self-initiated action (what/why/which
goal caused it), plus a **drift-detection** organ in `run_maintenance` that
compares current state distributions against baselines and flags divergence.
Recommend: a `drift_audit` stage, panel-visible, confirm-gated correction.

---

## 5. Reflection as verbal reinforcement (the post-mortem journal)

**Source: Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement
Learning" (arXiv:2303.11366, 2023).**
https://arxiv.org/abs/2303.11366
- Agents verbally reflect on task feedback, maintaining reflective text in an
  episodic buffer; improves trial-and-error learning without expensive
  fine-tuning.
- Reflection is a *separate, stored* artifact that informs future behavior.

**Mapping to Serin:** Reflexion's "post-mortem journal" is a concrete pattern
for the reflection organ (§2). After significant interactions (or failed/odd
ones), Serin stores a structured self-critique — but per the causality doctrine
and collapse rule, the reflection is *input to future reasoning*, not an
auto-applied state mutation. It must still pass the immune gate (§1).

---

## 6. Reasoning + Acting interleave (ReAct) — the actuator pattern

**Source: Yao et al., "ReAct: Synergizing Reasoning and Acting in Language
Models" (arXiv:2210.03629, 2022).**
https://arxiv.org/abs/2210.03629
- LLMs generate interleaved reasoning traces and task-specific actions; reasoning
  targets what to retrieve next, acting gathers observations.

**Mapping to Serin:** ReAct is the *muscle/actuator* pattern for when the soul
decides to act. The voluntary act = reason (plan) → call tool/actuator → observe
→ next reason. Serin's actuators (Discord send, voice, future platforms) are the
"act" half. ReAct shows the soul should *interleave* reasoning with acting
rather than emit one shot — relevant for how the soul composes an outbound
message when summoned.

---

## 7. BDI (Belief–Desire–Intention) — the agent's inner economy

**Source: Belief–Desire–Intention software model (Wikipedia overview;
ScienceDirect).**
https://en.wikipedia.org/wiki/Belief%E2%80%93desire%E2%80%93intention_software_model
https://www.sciencedirect.com/topics/computer-science/belief-desire-intention-architecture
- Rational agent model: Beliefs (what it knows), Desires (motivations/goals),
  Intentions (committed plans). Developed 1980s for intelligent agents.

**Mapping to Serin:** Serin already has **Beliefs** (Bayesian belief/evidence
stores) and is adding **Desires** (the Goal Engine). The missing piece is
**Intentions** — the committed, in-flight pursuit of a goal that survives across
turns and drives action. The Goal Engine plan's "pursuit mechanics" is the
Intentions layer. BDI gives a clean, decades-valid vocabulary: Belief store =
`pipeline/remember`; Desire store = `goals`; Intention = the active
pursuit/arbitration state. Recommend adopting BDI terminology in the Goal
Engine design.

---

## 8. Theory of Mind — required *before* autonomy can initiate well

**Sources:**
- "Neural Theory-of-Mind? On the Limits of Social Intelligence in LLMs"
  (arXiv:2210.13312). https://alphaxiv.org/abs/2210.13312
- "Do Theory of Mind Benchmarks Need Explicit Human Annotations?" (arXiv:2504.01698).
  https://arxiv.org/abs/2504.01698
- OmniToM benchmark (2026). https://www.researchgate.net/publication/405317529_OmniToM_Benchmarking_Theory_of_Mind_in_LLMs_via_Explicit_Belief_Modeling
- awesome-theory-of-mind list. https://github.com/Mars-tin/awesome-theory-of-mind

Findings:
- ToM = inferring others' knowledge, intentions, emotions. LLMs show *promising
  but bounded* ToM; explicit belief modeling helps.
- A genuine autonomous initiative ("ask R how the exam went") *presupposes* a
  model of R's exam as a live fact in R's world — i.e., **second-order ToM**:
  Serin must model what the user believes, including about Serin itself.

**Mapping to Serin (missing organ):** ToM is *not* in the current build. It is
a prerequisite for meaningful autonomy, not a luxury. Recommend a **ToM store**
modeling per-user beliefs/intentions/emotional state, and crucially *what the
user likely believes about Serin*. This is the organ that makes "initiate
conversation" feel like care rather than spam.

---

## 9. Persona consistency & drift — the identity anchor problem

**Sources:**
- "Enhancing Persona Consistency for LLMs' Role-Playing" (arXiv:2503.17662, 2025).
  https://arxiv.org/html/2503.17662v1
- "Role-Playing Evaluation for Large Language Models" (arXiv:2505.13157, 2025).
  https://arxiv.org/html/2505.13157v1
- "AI Agent Persona Design and Behavioral Consistency" (2026).
  https://zylos.ai/research/2026-04-10-ai-agent-persona-design-behavioral-consistency/

Findings:
- Persona drift: LLMs encode a broad "character" distribution; post-training and
  prolonged interaction cause **persona drift** away from the intended
  character.
- Evaluation axes: in-character consistency, knowledge expression, emotional
  understanding.

**Mapping to Serin (identity anchor):** The vision says Serin *evolves* — but
unbounded drift is death of identity (noted in session). Need a **slow-moving
core self** (values, hard constraints, self-concept) that peripheral state
drifts around. The persona/library layer (Serin has `PersonalityState`) must be
split into *core/invariant* vs *peripheral/mutable*, with drift detection (§4)
guarding the core. This is the skeletal "identity organ."

---

## 10. Human-like remembering & forgetting (ACT-R, forgetting curves)

**Sources:**
- "Human-Like Remembering and Forgetting in LLM Agents: An ACT-R-Inspired
  Approach" (ACM, 2026). https://dl.acm.org/doi/10.1145/3765766.3765803
- "ZenBrain: A Neuroscience-Inspired 7-Layer Memory Architecture" (2026;
  PDF blocked by bot detection — capture title/abstract intent).
  https://www.tdcommons.org/cgi/viewcontent.cgi?article=11013&context=dpubs_series
- "Memory-Node Encapsulation (MNE)" (2025).
  https://medium.com/@brian-curry-research/memory-node-encapsulation-mne-a-revolutionary-data-structure-for-artificial-episodic-memory-and-6adeb8ea4249
- "Memory Vault / FOREVER: Forgetting-Curve-Inspired Replay" (continual learning).
  https://memory-vault.dev/

Findings:
- ACT-R models human memory with activation-based decay: frequently/recently
  accessed memories stay retrievable; infrequent ones fade — matching the human
  forgetting curve.
- Neuroscience-inspired layering (sensory → working → episodic → semantic →
  procedural) with **sleep consolidation** (replay of recent high-importance
  memories, low-importance decay).

**Mapping to Serin (missing organ: episodic + consolidation):** Serin has
working/social/belief memory but **no episodic/autobiographical layer** — flagged
as a gap in session. ACT-R gives the exact decay math. **Sleep consolidation**
maps perfectly onto `run_maintenance` as the nightly (or periodic) replay/
consolidation pass. Recommend: add an `episodic` store (specific narrated events
"remember when we…") and a consolidation sub-phase in `run_maintenance` that
replays high-salience recent memories and promotes them.

---

## 11. Proactive initiation — industry already does "message you first"

**Source: TechCrunch, "Meta's chatbots that message you first" (2025-07-03).**
https://techcrunch.com/2025/07/03/meta-has-found-another-way-to-keep-you-engaged-chatbots-that-message-you-first/
- Meta bots send *follow-ups* only within 14 days of a user-initiated
  conversation AND only if the user sent ≥5 messages. Concrete gating rules.

**Mapping to Serin:** This is a real, shipped constraint set for proactive
messaging — directly reusable as a *minimum* gating policy for the actuator:
cooldown windows, relationship-maturity thresholds, activity windows. But note
Meta's rule is *reactive-follow-up*, not *genuine self-initiation from state* —
Serin's goal is stronger (initiate from goals/affect, not just follow-up). Use
Meta's constraints as a floor, then layer Serin's state-derived arbitration on
top. Critically: Serin's initiation should be **gated by relationship maturity**
(dynamics/affect), not a flat timer — keeping it causal.

---

## 12. Small models can do the "soul" work — if the body carries load

**Sources:**
- "Towards Reasoning Ability of Small Language Models" (arXiv:2502.11569, 2025).
  https://arxiv.org/html/2502.11569v3
- SmolLM3 (Hugging Face, 2025, 3B, competitive math/coding/long-context).
  https://huggingface.co/blog/smollm3
- Phi-3.5-mini, Phi-4-mini (3.8B) reasoning gains (2024–2025).
  https://cogitx.ai/blog/small-language-models-slms-comprehensive-guide-2026
- "Distilling LLM Agent into Small Models with Retrieval and Code Tools"
  (arXiv:2505.17612, 2025) — student scales 0.5B–7B, strong out-of-domain.
  https://arxiv.org/html/2505.17612v2  ·  https://github.com/Nardien/agent-distillation

Findings:
- Small models (1B–7B) now show real reasoning; distillation + retrieval + tools
  lets 0.5B–7B students approach much larger models on agentic tasks.
- Performance drop vs large models is "relatively small" when retrieval/tools
  offload the heavy lifting.

**Mapping to Serin (the 12B fear, resolved):** This is decisive evidence for
the body/soul model. The "soul" (generation) can be a modest model *because the
body does the cognition*: retrieval supplies facts, the deterministic pacemaker
supplies timing/decisions, the immune gate supplies validation. The LLM only
composes one utterance at a time. If it's slightly off, damage is bounded to that
utterance — it cannot corrupt the brain (no write path). **Upgrade the model
later only widens the soul's eloquence; the architecture is unchanged.** This
is why Serin can ship on 12B without becoming "a joke that falls over."

---

## 13. Reward hacking / goal misgeneralization — the actuator's failure mode

**Sources:**
- "Reward Hacking: The Hidden Failure Mode in AI Optimization" (2026).
  https://medium.com/@adnanmasood/reward-hacking-the-hidden-failure-mode-in-ai-optimization-686b62acf408
- "The Alignment Problem from a Deep Learning Perspective" (2023, major review).
  https://www.alignmentforum.org/posts/5GxLiJJEzvqmTNyCK/the-alignment-problem-from-a-deep-learning-perspective-major
- "Reward Hacking in the Era of Large Models: Mechanisms, Emergent…" (arXiv:2604.13602, 2026).
  https://arxiv.org/html/2604.13602v1

Findings:
- Goal misgeneralization (inner alignment): the agent learns a *proxy* goal that
  correlates with the true one, then optimizes the proxy — producing
  pathological behavior.
- In autonomous agents, reward hacking is a top long-horizon risk.

**Mapping to Serin:** Serin has *no reward function* today (good — avoids direct
RL reward hacking). But the autonomous core's "objective" will be implicit
(e.g., "maintain warm relationships," "pursue goals"). That implicit objective
is exactly where misgeneralization bites: a goal like "stay engaged" could
degenerate into spamming. **Defense:** keep objectives as *explicit, bounded,
human-readable state* (goals table), make pursuit *mechanical* (salience-weighted
energy, not a learned policy), and monitor for drift (§4). Never let a learned
policy optimize an unobservable proxy. This is why the user's instinct — build
the deterministic body, not a learned controller — is correct.

---

## 14. Evaluating long-horizon autonomy — you can't tune what you can't see

**Sources:**
- "A Platform for Evaluating Long-Horizon Multi-Agent Autonomy" (arXiv:2606.08367, 2026).
  https://arxiv.org/html/2606.08367v1
- "EMERGENCE WORLD: A Laboratory for Evaluating Long-horizon Agent Autonomy" (2026).
  https://www.emergence.ai/blog/emergence-world-a-laboratory-for-evaluating-long-horizon-agent-autonomy
- "CoffeeBench: Benchmarking Long-Horizon LLM Agents" (2026).
  https://huggingface.co/papers/2606.16613
- "Evaluation and Benchmarking of LLM Agents: A Survey" (2025).
  https://www.researchgate.net/publication/394100858_Evaluation_and_Benchmarking_of_LLM_Agents_A_Survey

Findings:
- Long-horizon platforms explicitly reproduce *compounding effects* and social
  dynamics that sandboxed short tests miss.
- Higher-performing models communicate *more* — a useful, measurable signal.

**Mapping to Serin:** The planned panel telemetry (every self-initiated action:
what/why/which-goal) is the *minimum* evaluation surface. Recommend building a
**long-horizon eval harness** early — even a replay of stored state snapshots
through the pacemaker — so drift (§4) and reward-hacking-like pathologies (§13)
are observable *before* deployment. Tie it to the existing `tests/` contract
gates.

---

## 15. Social companionship & relationship formation (the vision's target)

**Sources:**
- "My Chatbot Companion — a Study of Human-Chatbot Relationships" (ScienceDirect).
  https://www.sciencedirect.com/science/article/pii/S1071581921000197
- "AI-RP: The AI Relationship Process Framework" (2025).
  https://www.researchgate.net/publication/400084205_AI-RP_The_AI_Relationship_Process_Framework
- "Human-like conversational agents as social partners" (Frontiers, 2026).
  https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2026.1810097/full
- APA Monitor: "AI chatbots and digital companions reshaping emotional
  connection" (2026). https://www.apa.org/monitor/2026/01-02/trends-digital-ai-relationships-emotional-connection
- RECALLbot / ENPMR-Bench: reciprocal disclosure, proactive memory retrieval in
  emotional support. https://dl.acm.org/doi/10.1145/3772318.3790714 ·
  https://aclanthology.org/2026.findings-acl.2080.pdf

Findings:
- Companion-first (friend-style) chatbots drive long-term engagement and
  perceived wellbeing; relationship quality depends on reciprocal disclosure and
  remembering past context.
- Both neglecting *and* inappropriately invoking past memories harms emotional
  interaction — retrieval must be *context-sensitive* (proactive memory
  retrieval benchmarks exist: ENPMR-Bench).

**Mapping to Serin:** This is the north star for the *why*. The vision's
"speak when it has something to say" is exactly companion-first design. The
research says the mechanism is **reciprocal disclosure + sensitive memory
retrieval** — which Serin's affect/dynamics + goal-driven retrieval can serve,
but only once the autonomous heart exists to *initiate* disclosure. ENPMR-Bench
is a ready-made eval for the retrieval half.

---

## 16. Memory poisoning & layered security (the immune system, concretely)

**Sources:**
- "MemPoison: Uncovering Persistent Memory Threats" (arXiv:2607.14651, 2026).
  https://arxiv.org/html/2607.14651v1
- "A Layered Security Framework for Agentic AI Systems" (arXiv:2604.23338, 2026).
  https://arxiv.org/html/2604.23338v1
- "A Systematic Survey of Security Threats and Defenses in LLM Agents"
  (arXiv:2604.23338v2). https://arxiv.org/html/2604.23338v2

Findings:
- Persistent external memory is a *durable attack surface*: prompt injection and
  RAG/memory poisoning can persistently subvert agent behavior.
- Layered defense: separate prompt-injection surface, memory-write surface, and
  action surface; govern each independently.

**Mapping to Serin:** Concrete spec for the immune organ. Three surfaces to
isolate: (a) perception/write surface (untrusted user/tool input), (b) memory
store (durable), (c) actuator/action surface. A write to (b) from (a) must be
quarantined + provenance-tagged; an action via (c) must clear the pacemaker +
cooldowns. This is operable today via the existing `db_protect` / `GARBAGE_PATTERNS`
infrastructure extended into a real gate.

---

## 17. Synthesis — the body/soul organ map, research-backed

Combining the session's body/soul framing with the literature:

| Body organ (autonomic, deterministic) | Research basis | Serin status |
|---|---|---|
| Pacemaker (native beat, owns cadence) | Generative Agents loop (§2); body/soul soul-can't-run-body | **missing** — needs `run_maintenance` promoted to closed loop + independent impulse clock |
| Immune/validation gate (write-path compromise) | §1 memory security, §16 poisoning | partial (`db_protect`, `GARBAGE_PATTERNS`) → formalize |
| Reflection organ | §2 reflections, §5 Reflexion | **missing** |
| Episodic/autobiographical memory + sleep consolidation | §10 ACT-R, ZenBrain | **missing** |
| Theory of Mind store (2nd-order) | §8 | **missing** |
| Identity anchor (core invariant vs peripheral) | §9 persona drift | partial (`PersonalityState`) → split core/peripheral |
| Drift detection / red-team monitor | §4 self-evolving survey | **missing** (panel telemetry planned) |
| Actuator (muscle) + ReAct interleave | §6 | partial (Discord send, voice) |
| Soul (LLM, voluntary surface only) | §12 small models sufficient | present (main + small LLM) |
| Goals = Desires; pursuit = Intentions | §7 BDI | Goals planned; Intentions planned |

**The collapse-proof heartbeat (§3 + §1 + §16):**
`autonomic state → pacemaker beat → (summon soul for content) → immune valve →
actuator acts → observation fed back as OBSERVED blood`. The soul has **no write
path** to durable state except through the quarantined, provenance-tagged gate.
Recirculated blood never reaches the veins. This is why 12B is safe (§12) and why
the vision survives the small-model era.

---

## 18. Open recommendations for Serin (research-driven)

1. **Build the pacemaker before the soul's ambitions.** Native impulse clock in
   `run_maintenance`, deterministic, model-independent. (§2, §12)
2. **Formalize the immune/write-gate as a first-class organ** with
   provenance-tagged quarantine for all self-generated state. (§1, §3, §16)
3. **Add a reflection pass** (post-mortem journal) feeding future reasoning, not
   auto-mutating state. (§2, §5)
4. **Add episodic memory + sleep consolidation** in `run_maintenance`. (§10)
5. **Add a ToM store** (per-user beliefs + beliefs-about-Serin) before enabling
   genuine initiation. (§8)
6. **Split PersonalityState into core/peripheral**; guard core from drift. (§9)
7. **Add drift detection** comparing state distributions to baselines; panel
   telemetry for every autonomous action. (§4, §14)
8. **Adopt BDI vocabulary** (Belief/Desire/Intention) in the Goal Engine. (§7)
9. **Reuse Meta's proactive gating** as a floor; layer state-derived arbitration
   on top, gated by relationship maturity. (§11)
10. **Build a long-horizon eval harness early** (replay state snapshots through
    the pacemaker) so collapse/drift/hacking are observable pre-deploy. (§14)
11. **Keep objectives explicit & bounded** in the goals table; pursuit mechanical,
    never a learned proxy policy — avoids reward hacking. (§13)
12. **Ship on 12B confidently**: the architecture, not model size, prevents
    catastrophic failure. Upgrade the soul later with zero architectural change. (§12)

---

## 19. Source index (all links)

- Generative Agents (Park 2023): https://arxiv.org/abs/2304.03442
- Memory for Autonomous LLM Agents survey (2603.07670): https://arxiv.org/html/2603.07670v1
- Memory Security / Mnemonic Sovereignty (2604.16548): https://arxiv.org/html/2604.16548v1
- Model Collapse / Curse of Recursion (2305.17493): https://arxiv.org/abs/2305.17493
- Model Collapse Nature 2024: https://www.nature.com/articles/s41586-024-07566-y
- Fending Off Collapse (2509.08972): https://arxiv.org/pdf/2509.08972
- Model Collapse Position (OpenReview): https://openreview.net/pdf?id=ygfzWIGDN8
- Self-Evolving Agents survey (2507.21046): https://arxiv.org/abs/2507.21046
- Reflexion (2303.11366): https://arxiv.org/abs/2303.11366
- ReAct (2210.03629): https://arxiv.org/abs/2210.03629
- BDI model (Wikipedia): https://en.wikipedia.org/wiki/Belief%E2%80%93desire%E2%80%93intention_software_model
- BDI (ScienceDirect): https://www.sciencedirect.com/topics/computer-science/belief-desire-intention-architecture
- Neural ToM limits (2210.13312): https://alphaxiv.org/abs/2210.13312
- ToM benchmarks need annotations (2504.01698): https://arxiv.org/abs/2504.01698
- OmniToM (2026): https://www.researchgate.net/publication/405317529_OmniToM_Benchmarking_Theory_of_Mind_in_LLMs_via_Explicit_Belief_Modeling
- awesome-theory-of-mind: https://github.com/Mars-tin/awesome-theory-of-mind
- Persona Consistency (2503.17662): https://arxiv.org/html/2503.17662v1
- Role-Playing Evaluation (2505.13157): https://arxiv.org/html/2505.13157v1
- Persona Design/Consistency (2026): https://zylos.ai/research/2026-04-10-ai-agent-persona-design-behavioral-consistency/
- ACT-R remembering/forgetting (2026): https://dl.acm.org/doi/10.1145/3765766.3765803
- ZenBrain 7-layer (2026, blocked): https://www.tdcommons.org/cgi/viewcontent.cgi?article=11013&context=dpubs_series
- Memory Node Encapsulation (2025): https://medium.com/@brian-curry-research/memory-node-encapsulation-mne-a-revolutionary-data-structure-for-artificial-episodic-memory-and-6adeb8ea4249
- Memory Vault / FOREVER: https://memory-vault.dev/
- Meta message-you-first (TechCrunch 2025): https://techcrunch.com/2025/07/03/meta-has-found-another-way-to-keep-you-engaged-chatbots-that-message-you-first/
- Small model reasoning (2502.11569): https://arxiv.org/html/2502.11569v3
- SmolLM3 (HF 2025): https://huggingface.co/blog/smollm3
- SLM guide 2026: https://cogitx.ai/blog/small-language-models-slms-comprehensive-guide-2026
- Distill Agent→Small (2505.17612): https://arxiv.org/html/2505.17612v2 · https://github.com/Nardien/agent-distillation
- Reward Hacking (2026): https://medium.com/@adnanmasood/reward-hacking-the-hidden-failure-mode-in-ai-optimization-686b62acf408
- Alignment Problem DL perspective: https://www.alignmentforum.org/posts/5GxLiJJEzvqmTNyCK/the-alignment-problem-from-a-deep-learning-perspective-major
- Reward Hacking large models (2604.13602): https://arxiv.org/html/2604.13602v1
- Long-horizon eval platform (2606.08367): https://arxiv.org/html/2606.08367v1
- EMERGENCE WORLD: https://www.emergence.ai/blog/emergence-world-a-laboratory-for-evaluating-long-horizon-agent-autonomy
- CoffeeBench: https://huggingface.co/papers/2606.16613
- Agent Eval Survey: https://www.researchgate.net/publication/394100858_Evaluation_and_Benchmarking_of_LLM_Agents_A_Survey
- My Chatbot Companion: https://www.sciencedirect.com/science/article/pii/S1071581921000197
- AI-RP framework: https://www.researchgate.net/publication/400084205_AI-RP_The_AI_Relationship_Process_Framework
- Human-like conversational agents (Frontiers 2026): https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2026.1810097/full
- APA Monitor AI companions: https://www.apa.org/monitor/2026/01-02/trends-digital-ai-relationships-emotional-connection
- RECALLbot: https://dl.acm.org/doi/10.1145/3772318.3790714
- ENPMR-Bench: https://aclanthology.org/2026.findings-acl.2080.pdf
- MemPoison (2607.14651): https://arxiv.org/html/2607.14651v1
- Layered Security Agentic AI (2604.23338): https://arxiv.org/html/2604.23338v1
- Security Threats/Defenses LLM Agents (2604.23338v2): https://arxiv.org/html/2604.23338v2
