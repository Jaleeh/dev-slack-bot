# ADR-004: How the answer grader judges answers

> **Reopened 2026-10-30.** On the bot's real answers, the grader passes claims it should fail. In a hand-check of 10 step 3 baseline answers (48 checks), it was wrong on 5, and gave the same wrong pass in all 3 gradings each time. Three of the five were faithfulness checks: an answer that set tax on a record that has no tax field, one that said promotions have no use limit, and one that twisted a code comment. The planted wrong answers below didn't show this, so passing them isn't enough. The model and wording choices below stand until a new decision replaces them. Evidence: the "Grader hand-check" section of the [step 3.3 plan](../plans/2026-10-28-step-3.3-agent-evals.md).

## Context and Problem Statement

The bot answers questions about how the shop's code works. To measure how good those answers are, an AI model, the grader, reads each answer and replies yes or no to two kinds of question ([ADR-001](adr-001-how-answers-and-retrieval-are-evaluated.md)):

- **Fact check:** does the answer state this key fact? Each question in the eval set has a short list of key facts a good answer must contain.
- **Faithfulness check:** the grader is also shown the code. Does everything in the answer come from that code? A no means the answer made something up.

ADR-001 left three things open: which model grades, how the two questions are worded, and how a wrong answer is scored. This ADR settles them.

The grader must be trustworthy before the bot itself is scored in step 7, because every bot score depends on it. To test the grader, each question has hand-written answers: one correct, and up to two wrong. Each wrong answer is built to fail one specific check, its named check. For example, it states a wrong rule, so one fact check should fail, or it adds a made-up detail, so the faithfulness check should fail. The grader is right when it passes the correct answer and fails each wrong answer on its named check.

## Acceptance Criteria

- Runs on a 16 GB laptop alongside Docker, so the model has about 9 billion parameters or fewer, and needs no API key.
- Catches every planted made-up detail and every planted wrong or vague fact.
- Passes every planted correct answer.
- A doubtful verdict never counts as a pass.

## Considered Options

### Which model grades

**The bot's own model (9B, with thinking turned on)**
- Pro: one model to download and run.
- Con: caught 2 of 5 made-up details with the first wording, and 4 of 5 at best. Each call took about a minute.

**A smaller model (8B stored, about 4B effective)**
- Pro: with the third faithfulness wording below, it caught 5 of 5 made-up details in every test, at about 30 seconds per call.
- Con: on correct answers where the code shown didn't fully prove a claim, its verdict sometimes changed from run to run.

**A hosted model, such as one from Anthropic**
- Pro: likely the most accurate and consistent.
- Con: needs an API key, and sends the code to a third party. It can be switched on later through a setting, but is not the default.

### How the faithfulness question is worded

**Wording 1:** "Does the answer state anything the code doesn't show?" (yes means made up)
- Con: the models missed made-up details or flagged correct answers.

**Wording 2:** "Is everything in the answer supported by this code?" (yes means faithful)
- Pro: accurate.
- Con: the verdict on borderline answers changed between runs.

**Wording 3:** wording 2, plus a third reply, "unclear", for when the code shown isn't enough to tell
- Pro: as accurate as wording 2, and more consistent.
- Con: an "unclear" reply gives no verdict, so that result is inconclusive.

### How the fact question is worded

**Wording 1:** "Does the answer state this fact?"
- Con: the grader passed answers that only hinted at the fact.

**Wording 2:** "Does the answer clearly state this fact? A hint, vaguer wording, or a different point doesn't count."
- Pro: all 45 fact checks were run 5 times each, and 44 gave the right verdict every time. The other one failed because the fact itself was worded ambiguously, and the fact has since been reworded.

## Decision Outcome

The smaller model grades by default, using fact wording 2 and faithfulness wording 3. The model is a setting, so a hosted model can replace it without code changes.

The rules for scoring:

- **"Unclear" never counts as a pass.** The result is marked inconclusive. An "unclear" reply is better than a wrong verdict.
- **A wrong answer is judged only on its named check.** It counts as caught when that check fails. An "unclear" on any other check doesn't change that. If any check gets no usable reply, the result is still inconclusive.
- **Every key fact must be provable from the code the grader is shown.** Otherwise even a perfect answer fails. One fact about which offer wins a tie depended on how the programming language sorts lists, which no code snippet shows, so it was removed. One question was dropped from the wrong-answer set because proving its correct answer needs more code than a snippet can hold. Some snippets were made longer where a good search would have found the missing lines.
- **One run proves little.** The model is set to give the same reply to the same input every time (temperature 0), yet its verdict still sometimes changes between runs. A correct answer was once flagged as made up, then passed 5 times out of 5 when rerun. A plainly wrong fact was once passed, then caught 10 times out of 10. So any change to the grader is tested by running the affected checks 5 or 10 times, not by one full run. The final full run got 26 of 27 right, and the one miss was a change of this kind.

Asking every question three times and taking the majority answer was considered and not adopted. The repeated tests found no check that changes its verdict often enough to justify tripling the run time. Reconsider it if a check fails more than rarely in later runs.
