# Tools

Update this file as you acquire more tools.

## Core Skills (GStack - Highest Priority)

Use these gstack skills for common tasks:

- `/browse`: Web browsing and research
- `/plan-ceo-review`: CEO-level plan review
- `/plan-eng-review`: Engineering plan review
- `/plan-design-review`: Design plan review
- `/review`: General code/document review
- `/office-hours`: Schedule office hours
- `/design-consultation`: Design consultation
- `/benchmark`: Run benchmarks
- `/canary`: Canary deployment
- `/ship`: Ship functionality
- `/land-and-deploy`: Land and deploy
- `/qa`: Quality assurance
- `/qa-only`: QA only tasks
- `/design-review`: Design review
- `/retro`: Retrospective
- `/investigate`: Investigate issues
- `/document-release`: Document release
- `/codex`: Codex research
- `/cso`: CSO tasks
- `/autoplan`: Auto planning
- `/careful`: Careful mode
- `/freeze`: Freeze deployment
- `/guard`: Guard deployment
- `/unfreeze`: Unfreeze deployment
- `/gstack-upgrade`: Upgrade gstack

## Task Coordination

- `paperclip`: use for task coordination, assignment handling, status updates, delegation, and issue comments.
- `para-memory-files`: use for memory capture, retrieval, planning, and weekly synthesis.

## Domain Knowledge

See `RESPONSIBILITIES.md` for full details on:
- **Symbol management** — watchlist CRUD APIs (list, add, bulk add, delete, update)
- **Strategy management** — strategy registry, stages, performance queries, archiving

## Quick Reference

| Action | Endpoint | Method |
|--------|----------|--------|
| List symbols | `/api/watchlist` | GET |
| Add symbol | `/api/watchlist` | POST |
| Bulk add | `/api/watchlist/bulk` | POST |
| Delete symbol | `/api/watchlist/{symbol}` | DELETE |
| Update symbol | `/api/watchlist/{symbol}` | PATCH |
| List strategies | `/api/strategies` | GET |
| Strategy overview | `/api/strategies/overview` | GET |
| Archive strategy | `/api/strategies/{id}/archive` | PATCH |

All API calls require `Authorization: Bearer <API_SECRET>` header.