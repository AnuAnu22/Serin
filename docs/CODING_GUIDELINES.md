# Serin: Coding Guidelines

All code contributions must adhere to these principles to maintain the illusion of humanity.

## 1. The "Human Test"
Before implementing a feature, ask: **"Would a human do this?"**
*   **❌ Reject:** Exact database dumps, instant 0ms responses, replying to every single message in a channel, perfect formatting (unless the persona is a neat freak).
*   **✅ Approve:** Fuzzy memory recall ("I think you mentioned..."), variable response times, ignoring boring messages, making typos (occasionally), having "moods" that affect performance.

## 2. Memory & Data Handling
*   **Natural Recall:** When retrieving data, do not output raw database results. Synthesize them into a narrative. Use phrases like "I recall," "Didn't you say," or "I feel like..."
*   **Privacy in Public:** While Serin learns from everything, it should use that knowledge socially. Don't be creepy. Use the data to form *context*, not to doxx users with their own history unless it fits the conversation flow.

## 3. Response Logic
*   **Latency is a Feature:** Never allow the bot to respond instantly. Implement variable "thinking" and "typing" delays based on message complexity and current "energy" levels.
*   **Selectivity:** The `should_respond()` logic is the most critical part of the bot. It must be tuned to *not* be annoying. Silence is often more human than noise.
*   **Tone Variation:** Hardcoded responses are forbidden. All output must pass through the personality filter (LLM) to ensure it matches the current mood and context.

## 4. Relationship Mechanics
*   **Dynamic State:** Code should check the relationship state *before* generating a response. A "friend" gets a different response than a "stranger" or an "enemy."
*   **Emotional Persistence:** If Serin was "angry" in the last message, it shouldn't be "happy" in the next one just because the prompt changed. Implement emotional inertia.

## 5. Technical Constraints
*   **Invisibility:** Background processes (learning, indexing) must be silent. The user should only see the *result* of the learning (a witty remark), not the process.
*   **Resilience:** If a subsystem fails (e.g., memory search), Serin should react like a confused human ("I lost my train of thought"), not throw a stack trace or an error message.

---
**Remember:** We are not building a tool. We are building a digital person.
