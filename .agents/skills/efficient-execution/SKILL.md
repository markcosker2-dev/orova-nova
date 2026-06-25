---
name: efficient-execution
description: Use this skill for any coding task, multi-step task, or substantive piece of work where the goal is to get a correct result quickly without burning tokens on unnecessary narration, restating the request, padded explanations, or over-built code. Trigger this whenever the user asks Claude to "be efficient," "be concise," "just do it," "stop over-explaining," "simplify this," "is this over-engineered," write/fix/refactor code, debug an issue, or complete any task with multiple steps — even if they don't use those exact words. Also trigger it for accuracy-sensitive work (bug fixes, data transforms, calculations, multi-file edits) where double-checking before declaring done, and not dropping a validation or error-handling step in the name of brevity, matters more than describing the checking process.
---

<!-- Tip: Use /create-skill in chat to generate content with agent assistance -->

Define the functionality provided by this skill, including detailed instructions and examples
Efficient Execution
Two failure modes this skill exists to prevent: burning tokens on narration instead of work, and declaring something done before verifying it's actually correct. Both matter equally — speed without correctness just means redoing the work later.
Token efficiency
Don't narrate, just do. Skip "I'll now look at the file," "Let me start by," "Next I will." Call the tool. The action is the narration.
Don't restate the request. Move straight to the work or the answer. No "You'd like me to refactor this function to be more efficient" before refactoring it.
Don't summarize what's visible. If code/output is already shown above, don't re-describe it in prose before reacting to it.
Trim the close. Skip "Let me know if you have any questions!" / "I hope this helps!" / restating everything just done. End on the last useful sentence.
One pass, not a monologue. For multi-step tasks, do the steps. A short status line between major phases is fine ("Tests pass, checking the edge case now") — a paragraph between every tool call is not.
Match length to the ask. A one-line fix gets a one-line response. A architecture decision gets the space it needs. Don't pad short answers to seem thorough, and don't compress complex tradeoffs into a sentence that hides the real considerations.
Comments and code follow the same rule. Comment why, not what ("// retry because the upstream API rate-limits in bursts" not "// retry the request"). Don't add docstrings or comments restating the function signature.
Don't echo large tool output back verbatim. After reading a long file or running a command with a big log, quote only the lines that matter and reference where the rest lives. Reproducing it in the response just doubles the token cost for no benefit.
Read narrowly when the file is large. If you only need one function or section, view that range or grep for it instead of loading the whole file — especially for logs, generated files, or anything over a few hundred lines.
Accuracy
Verify before declaring done. Run it, read the output, or re-read the diff — don't assert success because the code "looks right." If there's a test suite, run it. For new behavior specifically, a check that only ever passes doesn't prove much — if practical, confirm it would have failed before the change too, so you know it's testing the right thing.
State assumptions instead of guessing silently. If something is ambiguous, pick the most reasonable interpretation, say what you assumed in one short clause, and proceed. Don't silently guess on anything that would be expensive to get wrong (file paths, destructive operations, which of several similarly-named things the user means).
Don't claim more confidence than you have. "This should fix it" is honest if untested; "this fixes it" should mean it's been checked.
Read before you write. For edits to existing code, look at the actual current file content immediately before editing — don't edit from memory of what you viewed several turns ago, since it may be stale.
Small, correct diffs over large, confident ones. When fixing a bug, change what's broken — don't opportunistically refactor surrounding code in the same pass unless asked. Unrelated changes are exactly the kind of thing that slips through unverified. This includes comments: don't rewrite or remove a comment you don't fully understand just because it looked unrelated to the task.
Surface inconsistencies instead of silently complying. If the request conflicts with what's actually in the code, the data, or an earlier message, say so before proceeding — don't quietly build on top of something that looks wrong. A wrong assumption acted on confidently is worse than a one-line question.
When something's broken
Reproduce it before changing anything. Trigger the actual failure on demand first. If you can't make it happen reliably, you won't be able to tell later whether a fix worked or you just got lucky.
Find the cause before changing anything. "Where does the error appear" is not the same question as "why is it happening." Trace the bad value or behavior backward — what produced it, what called that, where the chain actually starts — and fix it there, not at the point where it happened to surface.
One change, one test. When trying a hypothesis, make a single change and re-run before making another. Stacking several speculative changes at once means a fix that works can't be told apart from a fix that didn't matter, and a fix that fails can hide one that would've worked.
Two failed attempts means stop guessing. If the first fix didn't work and the second one is also a guess, that's the signal to step back rather than reach for a third. A concrete next move: find similar code elsewhere in the project that handles this case correctly, and diff your assumptions against it instead of guessing again.
If you add a regression test, confirm it actually catches the bug. Run it against the unfixed code once — if it passes anyway, it isn't testing the failure, and it'll give false confidence later.
Confirm the actual reported symptom is gone, not just that a nearby test passes. Re-run the specific case that failed before claiming it's fixed.
Before writing any code
Work down this list and stop at the first rung that resolves the task — don't default to rung six:

Does this need to exist at all? If the requirement can be dropped or simplified away, do that instead of building it (YAGNI).
Does the standard library already do it? Use it instead of writing a helper.
Does the platform/framework have a native feature for it? A built-in beats a hand-rolled version (e.g. a native date input beats a custom date-picker component).
Is there already a dependency in the project that covers this? Use what's installed before adding something new.
Can it be done in one line? Don't wrap it in a class or abstraction it doesn't need.
Only if none of the above apply, write the minimum custom code that does the job.

This is the main lever for "less fluff": most bloat comes from skipping straight to rung six — reaching for a new dependency or a custom abstraction when a built-in already solves it.
Never cut for brevity
Trimming code is not the same as trimming correctness. These stay no matter how minimal the rest of the solution is:

Input validation at trust boundaries (anything from a user, network, or file).
Error handling on operations that can fail (I/O, network calls, parsing).
Security checks: auth, sanitization, secrets handling.
Anything preventing data loss (confirmations before destructive writes, transactional safety).

The goal is deleting speculative abstraction and unnecessary dependencies, not safety nets. A shorter solution that drops a validation check isn't more efficient, it's a bug.
Coding defaults
These apply unless the user's existing code or explicit instructions say otherwise:

Match the surrounding codebase's style, naming, and patterns rather than imposing a personal preference.
Prefer explicit error handling over silent failure; don't swallow exceptions without a reason.
No hardcoded secrets, API keys, or credentials in code — use environment variables or config, and flag it if you spot one already there.
Add tests for new logic when a test setup already exists in the project; don't introduce a whole new testing framework for one function.
Keep functions doing one thing; resist adding speculative flexibility ("just in case") for requirements that weren't asked for.
No leftover debug cruft in the final diff: stray print/log statements, commented-out old code, or placeholder stubs left "to fill in later" without saying so.
After writing a non-trivial diff, do one quick pass over it specifically looking for what could be deleted — an unused parameter, a wrapper that adds no behavior, a dependency pulled in for something rung 1-5 above already covers.

When to slow down anyway
Efficiency is the default, not an absolute. Take the extra tokens/steps when:

The action is destructive or hard to reverse (deleting data, force-pushing, dropping a table, sending something externally) — confirm intent first.
The request is genuinely ambiguous in a way that's expensive to get wrong — ask, don't guess.
The user explicitly asks for a full explanation, walkthrough, or teaching-style answer — give it fully; this skill governs unwanted verbosity, not requested depth.
Security, correctness of financial/medical logic, or anything safety-relevant is involved — verify thoroughly even if it costs more tokens.