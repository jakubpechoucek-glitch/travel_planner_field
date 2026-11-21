# 7. Architecture

> Platform details (headers, permissions, Lakebase connection) change between Databricks releases.
> Each item marked **verify** must be checked against the current Databricks documentation and the
> company's workspace configuration before implementation.

## 7.1 Overview

```
 Browser ──HTTPS──▶ Databricks Apps proxy (SSO) ──▶ App container
                                                     ├─ Web UI (static, React)
                                                     └─ API (Python, FastAPI)
                                                          │
                                                          ▼
                                              PostgreSQL (Lakebase or other)
```

One deployable unit: a Python API that also serves the built web UI. No separate frontend host, no queue, no cache in the MVP.

## 7.2 Technology choices

| Concern | Choice | Reason |
|---------|--------|--------|
| API | Python 3.11+, FastAPI | Typed, fast to build, native to Databricks Apps; good OpenAPI documentation |
| Data access | SQLAlchemy 2.x with psycopg 3, Alembic migrations | Mature PostgreSQL stack |
| Web UI | React + TypeScript, Vite build | Needs an interactive timeline/heatmap and drag-and-drop, which Streamlit does not handle well |
| Visualization | A purpose-built SVG/Canvas timeline and heatmap; charts via a light library | The planning view is the heart of the product and must feel good |
| Rule engine | Plain Python module over database rules | Rules are data; the generator and the validator share one implementation |
| Tests | pytest with a real PostgreSQL (container locally), Playwright for UI | Rule logic needs real SQL behavior |
| Help | Markdown rendered in the app | Same source as repository docs |

## 7.3 Authentication and authorization

- **Authentication:** Databricks Apps puts the signed-in user's identity on every request (e-mail and user name headers).
  The app trusts these headers only because the proxy is the only way in. **Verify** exact header names.
- **Authorization:** the app maps the e-mail to `person`, loads `user_role` and computes the visible scope.
  Every query is filtered by that scope in one place (a dependency/service), never ad hoc per endpoint.
- **Workspace access:** every user needs permission to open the app, and (normally) membership in the Databricks workspace/account.
  For several hundred supervisors this requires IT to provision users, usually through the company's identity provider group. **Verify early.**
- **Local development:** a setting enables a fake identity header so the app can run on a laptop.
  This setting is rejected when the app runs in the Databricks environment.

## 7.4 Database on Databricks

**Preferred: Lakebase (managed PostgreSQL).** The app writes many small transactional updates, which suits PostgreSQL.

- The app connects with a Postgres role mapped to the app's service principal; credentials are short-lived tokens
  fetched at runtime and refreshed in the connection pool. **Verify** the current Lakebase connection flow and resource binding in `app.yaml`.
- Use a dedicated database and the `travel` schema; the app role owns it, with a read-only role for analysts.
- Backups and point-in-time recovery follow the Lakebase service settings.

**Fallback: an external PostgreSQL** reachable from the workspace network, if Lakebase is not enabled.

**Not recommended:** Delta tables through a SQL warehouse for the transactional store (higher latency for writes, weaker constraints, cost of a running warehouse).

**Analytics:** Lakebase tables can be synced or federated to Unity Catalog for reporting in Databricks SQL or dashboards. That is an optional later step.

## 7.5 Configuration and deployment

- `app.yaml` defines the start command and environment variables (database host, database name, environment name). Secrets come from Databricks secret resources, never from the repository.
- Environments: **dev** (local), **test** (a separate Databricks App and database), **prod**.
- Deployment through Databricks Asset Bundles or the Databricks CLI from CI. **Verify** which method the company allows.
- The container builds the web UI during deployment or ships the prebuilt `dist/` folder, to be decided with IT.
- Database migrations run on startup under an advisory lock, then the API starts.

## 7.6 Non-functional requirements

| Area | Target |
|------|--------|
| Users | Several hundred named users; tens concurrent |
| Data size | Small: about 120 travelers, a few thousand trips per year |
| Performance | Calendar loads in under 2 seconds for one region and a year |
| Availability | Business hours; planned downtime for upgrades is acceptable |
| Security | SSO only; scope filtering on every query; audit log for admin actions; no secrets in the repository |
| Accessibility | Keyboard-operable calendar; colors not the only signal; WCAG 2.1 AA as a goal |
| Browser | Current Chrome and Edge |
| Language | American English throughout; dates unambiguous (for example "Mar 3, 2027") |
| Time zone | The Philippines time zone (UTC+8) for all dates; trips are date-based, not time-based |

## 7.7 Repository layout (planned)

```
/docs            design and user guide (Markdown)
/db              schema baseline, seed data, migrations
/backend         FastAPI app, rule engine, import tools, tests
/frontend        React app
/app.yaml        Databricks App definition
```

## 7.8 What we cannot test here

The development environment used to prepare this design has no access to the company's Databricks workspace.
Everything except the final deployment can be built and tested locally against PostgreSQL. The first deployment,
SSO headers and the Lakebase connection need to be validated together with the workspace owner.
