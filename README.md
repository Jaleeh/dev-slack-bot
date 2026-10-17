# dev-slack-bot

A self-hosted chat bot that answers questions about your GitHub repositories, so project managers and support staff can get answers without interrupting a developer.

Ask it in Slack how a business rule works, or whether a reported problem is a bug or a setup issue. It reads your code and replies in the thread. It never changes code.

> **Status:** design only. No code exists yet. See the [architecture design doc](design-doc.html).

## Why

- **Fewer interruptions.** Routine "how does X work?" questions go to the bot, not a developer.
- **Your data, your choice.** You host it and pick the model provider and region, so you decide which country your data reaches. The project runs no servers and collects nothing.
- **Cheap to run.** Two containers (app and Postgres), per-question token limits, and prompt caching where supported. Run a local model with Ollama and tokens cost nothing.

## Planned features

### First release

- Answers questions about connected repositories, read only
- Slack, plus a browser chat for trying it out
- Any model provider through one setting: Anthropic, OpenAI, AWS Bedrock, Azure OpenAI, Google Vertex, Ollama
- Two retrieval methods, direct repository search and vector search, compared with evals
- A setup wizard so a non-technical admin can configure it
- Encrypted secrets that never return to the browser

### Two ways to run

| | Try it locally | Self-host for real |
|---|---|---|
| Start | `docker compose up` on a laptop | Same image, on your own server or cloud |
| Chat | Browser chat in the admin UI | Slack |
| Repositories | Public GitHub URL or local folder | Your own GitHub App |
| Model | Ollama or a pasted API key | Your chosen provider and region |

### Build order

1. Skeleton: FastAPI and Next.js connected, Postgres, Docker Compose, Makefile (CI follows once the GitHub repository exists)
2. Evals: labelled questions over a public sample repo, plus planted fake PII
3. Direct retrieval: LangGraph agent with `grep` and `read_file`
4. PII redactor
5. Browser chat and trial mode
6. Slack
7. Vector retrieval, compared against direct retrieval with the evals

### Future scope

- Microsoft Teams
- Reading logs, configuration and tickets, not just code
- Creating Jira tickets
- Prioritising issues
- Fixing bugs

Every write action waits for someone to press confirm in the chat thread.

## Where your data goes

The bot sends questions and code to the model and embedding providers you configure. Where that data goes depends on your choice:

| Provider | Data location |
|---|---|
| Ollama, vLLM | Your own machine or server |
| AWS Bedrock, Azure OpenAI, Google Vertex | The cloud region you select |
| Anthropic API, OpenAI API | Mostly the US |

The admin UI shows this next to each provider.

### PII redaction

Before anything reaches a model or embedding provider, personal data and secrets are swapped for typed placeholders. Real values are put back before the reply reaches the user.

```text
You ask:        Why can't Jane Citizen (jane@acme.com) log in?
Model sees:     Why can't <PERSON_1> (<EMAIL_1>) log in?
You get back:   Jane Citizen's account ... (real values restored)
```

- Applies to every provider call: your question, code the bot reads, and code sent for indexing
- The same person gets the same placeholder for a whole thread
- Logs, traces and chat history store only redacted text
- Detection runs locally inside the container (Microsoft Presidio), on by default
- An allow-list stops company, product and code names being hidden by mistake

Detection is not perfect, so your choice of provider and region is still the second line of protection.

## Tech stack

FastAPI, LangGraph, Postgres with pgvector, Presidio, Slack Bolt and Next.js, packaged with Docker Compose. Full list in [docs/tech-stack.md](docs/tech-stack.md).

## Documentation

- [Architecture design doc](design-doc.html): system shape, constraints, decisions and open questions
- [Tech stack](docs/tech-stack.md): every tool, its purpose, and what was rejected
- [Project structure](docs/project-structure.md): folder layout, import rules, test layout
- [`docs/adrs/`](docs/adrs/): architectural decision records
- [`docs/specs/`](docs/specs/) and [`docs/plans/`](docs/plans/): slice specs and implementation plans

## Licence

MIT. The `LICENSE` file is added with the first public commit.
