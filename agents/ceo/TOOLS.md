# Tools

Update this file as you acquire more tools.

## Core Skills

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