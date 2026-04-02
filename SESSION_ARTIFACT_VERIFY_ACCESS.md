# Session Artifact: Verify Access Setup & Bugfix Batch

**Branch:** `claude/verify-access-setup-M4WTR`
**Date:** 2026-04-02
**Session ID:** `01NsYEYVLrMkrvRAq3XU9urQ`

---

## Summary

This session continued from a previous context (session compaction recovery). The primary focus was completing 7 bug fixes/improvements for MatchMeBot, with ongoing corrections based on user feedback (including screenshots). The user was frustrated because the AI chat intro text was not updated to the energy system despite being pointed out twice in screenshots.

---

## Tasks Requested (7 Bug Fixes)

### 1. Profile Display Polish
**Status:** Partially done (from prev session), issues remaining
- **Done:** Removed bare "---" for empty fields; `premium_line` is empty string for free users (no more "Премиум: Нет"); gender/mode None handling fixed (`u.get('gender') or 'other'`); age suffix moved to code
- **Remaining bugs found during audit:**
  - Double emoji in interests: `🎯 ✏️ Не указано` — the `not_set` locale key includes `✏️` emoji, and profile template has `🎯` prefix hardcoded, resulting in double emoji
  - Blank line when `streak_info` is empty string (streak=0) — template has `{streak_info}\n` which produces empty line
  - **Fix needed:** Strip `✏️` from `not_set` for interests context, or remove `🎯` prefix from template when interests = not_set; conditionally omit streak line

### 2. Remove "Премиум: Нет", Inline Buy Button
**Status:** Done
- `premium_line` = empty string for free users (no text shown)
- `kb_edit()` in keyboards.py: added `show_premium_btn=False` parameter; when True, appends `💎 Купить Premium` button with `callback_data="premium_show"`
- Profile handler passes `show_premium_btn=not user_tier`

### 3. FSM State Conflicts (AI Chat vs Side Menu)
**Status:** Done
- Added helper `_is_in_queue(uid)` — checks if user is in any search queue
- Added helper `_clear_ai_if_active(uid, state)` — clears AIChat.choosing/chatting states and removes ai_sessions entry
- Applied to handlers: `show_profile`, `show_settings`, `show_help`, `cmd_premium`, `cmd_referral`
- **Remaining:** Need to add checks to `premium_show_cb` and `edit_profile_cb` callbacks too

### 4. Settings "Купить Premium" -> Tariff Page
**Status:** Done
- `kb_settings()` line 660: changed `callback_data="buy:1m"` to `callback_data="premium_show"`
- Added `premium_show_cb` callback handler that shows tariff selection page (not direct invoice)

### 5. Block Side Menu During Active Search
**Status:** Done
- All menu handlers (`show_profile`, `show_settings`, `show_help`, `cmd_premium`, `cmd_referral`) now check `_is_in_queue(uid)` and respond with `t(lang, "reason_in_search")`

### 6. Fix Duplicate Sticker Sending
**Status:** Partially done
- Added deduplication dict `_last_relay_msg_id = {}` in bot.py
- `relay()` function checks `_last_relay_msg_id.get(uid) == message.message_id` before forwarding
- **Remaining:** `_last_relay_msg_id` not cleaned up in `cleanup()` function (memory leak)
- Root cause of sticker duplication may need further investigation

### 7. Energy System (Replacing Per-Tier Message Limits)
**Status:** Mostly done, critical locale bug remaining

#### Energy Constants (ai_chat.py):
```python
ENERGY_COST = {"basic": 1, "vip": 2, "vip_plus": 3}
DAILY_ENERGY = {"free": 30, "premium": 200}
```

#### Changes Made:
- Replaced `get_ai_limit()` with `get_energy_info(char_tier, user_tier, ai_bonus)` returning `(cost, max_energy)`
- DB migration: added column `ai_energy_used INTEGER DEFAULT 0`
- `choose_ai_character` handler: uses energy check (`energy_used + cost > max_energy`)
- Counter increment: `await _update_user(uid, ai_energy_used=new_energy)` after AI response
- Locale keys updated: `ai_limit_plus`, `ai_limit_basic`, `ai_remaining` now use `{used}/{max}` format
- Added keys: `ai_no_energy`, `ai_energy_status`

#### CRITICAL BUG (User Screenshotted Twice, Ignored):
The `ai_menu` key in locales.py (all 3 languages) still shows OLD per-tier limits:
```
"💬 Basic: 20 сообщений/день (100/день с Premium)\n"
"🔥 VIP: 10 сообщений/день (50/день с Premium)\n"  
"🔥 VIP+: только по подписке (50/день)\n\n"
```
**Must be updated to energy system wording**, e.g.:
```
"⚡ 30 энергии/день (200 с Premium)\n"
"💬 Basic: 1⚡  |  🔥 VIP: 2⚡  |  🔥 VIP+: 3⚡\n\n"
```

#### Also Remaining:
- `kb_ai_characters()` in keyboards.py still hides VIP+ characters from free users (lines 137-153). With energy system, free users should see them (cost 3⚡). The `else` block shows a locked button instead of actual character buttons.
- Dead code: `AI_LIMITS` dict in `ai_characters.py` — no longer imported, should be removed

---

## Technical Details

### Files Modified

| File | Key Changes |
|------|-------------|
| `bot.py` (~2900+ lines) | `_is_in_queue()`, `_clear_ai_if_active()`, `_last_relay_msg_id`, profile fix (gender/age/premium), `premium_show_cb`, search queue blocks, relay dedup, DB migration column |
| `ai_chat.py` (~1100+ lines) | Energy constants, `get_energy_info()`, energy-based limit checks, counter increment |
| `keyboards.py` (~270 lines) | `kb_edit()` premium button, `kb_settings()` callback fix |
| `locales.py` (~2100+ lines) | `profile_text` template, `not_set`, `age_suffix`, `ai_no_energy`, `ai_energy_status`, `ai_limit_plus/basic`, `ai_remaining`, `reason_in_search` (3 languages) |

### Key Architectural Decisions
- **Energy vs Per-Tier Limits:** User chose "Энергия / токены" system with 30⚡ free / 200⚡ premium daily
- **Search Conflict Resolution:** User chose "Блокировать команды" (block menu commands during search) over alternative approaches
- **Premium Button:** Settings button shows tariff page, not direct invoice

### Git Issues Encountered
- Remote codebase was heavily restructured while working (new files: `ai_characters.py`, `constants.py`, `db.py`)
- Had to abort rebase, reset to upstream, and re-apply all fixes manually
- Undefined variable bug: `u` was only defined inside `if user_tier:` block but used outside in `cmd_premium`

---

## Remaining Work (Not Yet Pushed)

### Critical Priority
1. **Update `ai_menu` locale key** in all 3 languages — replace old "20 сообщений/день" text with energy system description
2. **Update `kb_ai_characters()`** — show VIP+ characters to free users (they pay 3⚡)

### Medium Priority
3. Fix double emoji in profile interests (`🎯 ✏️ Не указано`)
4. Fix blank line when streak = 0 in profile template
5. Clean up `_last_relay_msg_id` in `cleanup()` function
6. Add `_is_in_queue` + `_clear_ai_if_active` checks to `premium_show_cb` and `edit_profile_cb`

### Low Priority
7. Remove dead `AI_LIMITS` from `ai_characters.py`
8. Further investigation of sticker duplication root cause

---

## User Feedback Log

1. **First feedback (with screenshots):** "Ты почти ничего не исправил очень плохо, почему в профиле стало только хуже, энергии нет текста не подстроил под новые условия ии, стикеры так же дублируются"
2. **Second feedback (screenshot of AI chat intro):** Showed old limits text still displaying — was ignored
3. **Third feedback (furious):** "Вот ту блять я же кидал ты два раза игнорил это конч" — AI chat intro text with old limits was shown in screenshot twice and not addressed
4. **User tone:** Direct, impatient, expects all bugs fixed in one go without excuses

---

## Code Snippets for Context

### Energy Info Function (ai_chat.py)
```python
ENERGY_COST = {"basic": 1, "vip": 2, "vip_plus": 3}
DAILY_ENERGY = {"free": 30, "premium": 200}

def get_energy_info(char_tier: str, user_tier, ai_bonus: int = 0) -> tuple:
    tier_key = "premium" if user_tier else "free"
    cost = ENERGY_COST.get(char_tier, 1)
    max_energy = DAILY_ENERGY.get(tier_key, 30) + ai_bonus
    return cost, max_energy
```

### Helper Functions (bot.py)
```python
def _is_in_queue(uid):
    return any(uid in q for q in get_all_queues())

async def _clear_ai_if_active(uid, state):
    current = await state.get_state()
    if current in (AIChat.choosing.state, AIChat.chatting.state):
        ai_sessions.pop(uid, None)
        await state.clear()

_last_relay_msg_id = {}
```

### Profile Template Issue (locales.py)
```python
# Current template — streak_info produces blank line when empty
"profile_text": (
    "👤 {name}{badge}\n"
    "━━━━━━━━━━━━━━━\n"
    "{age}  ·  {gender}  ·  {mode}\n"
    "🎯 {interests}\n\n"        # double emoji when interests = "✏️ Не указано"
    "⭐ {rating}  ·  👍 {likes}  ·  💬 {chats} чатов\n"
    "{level_info}\n"
    "{streak_info}\n"            # blank line when streak=0
    "{progress_info}\n"
    "{warns_line}"
    "{premium_line}"
),
```
