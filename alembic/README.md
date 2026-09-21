# Alembic migrations

Set `DATABASE_URL` before running migrations. The default is the local SQLite
prototype database.

```powershell
python -m alembic upgrade head
python -m alembic downgrade base
```
