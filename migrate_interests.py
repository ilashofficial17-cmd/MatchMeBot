"""
One-time migration: convert old Russian interest strings in DB to locale keys.

Old format: "Разговор по душам 🗣,Юмор и мемы 😂"
New format: "int_talk,int_humor"

Run once: python migrate_interests.py
"""

import asyncio
import os
import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL")

OLD_TO_NEW = {
    # simple
    "Разговор по душам 🗣": "int_talk",
    "Юмор и мемы 😂":       "int_humor",
    "Советы по жизни 💡":    "int_advice",
    "Музыка 🎵":             "int_music",
    "Игры 🎮":               "int_games",
    # flirt
    "Лёгкий флирт 😏":       "int_flirt_light",
    "Комплименты 💌":         "int_compliments",
    "Секстинг 🔥":            "int_sexting",
    "Виртуальные свидания 💑": "int_virtual_date",
    "Флирт и игры 🎭":        "int_flirt_games",
    # kink
    "BDSM 🖤":               "int_bdsm",
    "Bondage 🔗":            "int_bondage",
    "Roleplay 🎭":           "int_roleplay",
    "Dom/Sub ⛓":            "int_domsub",
    "Pet play 🐾":           "int_petplay",
    "Другой фетиш ✨":        "int_other_fetish",
}

def migrate_value(raw: str) -> str:
    """Convert comma-separated interest string. Already-migrated keys pass through."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    result = []
    for p in parts:
        if p.startswith("int_"):
            result.append(p)          # already a locale key
        elif p in OLD_TO_NEW:
            result.append(OLD_TO_NEW[p])
        else:
            print(f"  [WARN] unknown interest value, skipping: {repr(p)}")
    return ",".join(result)

async def run():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT uid, interests FROM users WHERE interests IS NOT NULL AND interests != ''"
        )

    print(f"Found {len(rows)} users with interests")
    updated = 0
    skipped = 0

    async with pool.acquire() as conn:
        for row in rows:
            uid = row["uid"]
            old = row["interests"]

            # Skip if already fully migrated (all values start with int_)
            parts = [p.strip() for p in old.split(",") if p.strip()]
            if all(p.startswith("int_") for p in parts):
                skipped += 1
                continue

            new_val = migrate_value(old)
            if new_val != old:
                await conn.execute("UPDATE users SET interests=$1 WHERE uid=$2", new_val, uid)
                print(f"  uid={uid}: {repr(old)} → {repr(new_val)}")
                updated += 1

    await pool.close()
    print(f"\nDone. Updated: {updated}, already up-to-date: {skipped}")

if __name__ == "__main__":
    asyncio.run(run())
