# Revit MCP: שליטה ב-Revit מתוך Claude

מאפשר ל-Claude לקרוא מידע מהמודל ב-Revit, ליצור אלמנטים ולערוך אותם, ישירות מתוך שיחה.

```
Claude Desktop  ──MCP──►  revit_mcp_server.py  ──HTTP 127.0.0.1:8765──►  RevitMcp.dll (בתוך Revit)
```

- **addin/**: תוסף ל-Revit (C#). נטען כש-Revit עולה ופותח שרת מקומי שנגיש רק מהמחשב עצמו.
- **server/**: שרת MCP (Python) ש-Claude Desktop מפעיל.

תואם ל-**Revit 2024, 2025, 2026**.

## התקנה (פעם אחת)

דרישות: Windows, Revit, [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0), [Python 3.10 ומעלה](https://www.python.org/downloads/), [Claude Desktop](https://claude.ai/download).

1. מורידים את התיקייה `revit-mcp` למחשב (למשל `C:\revit-mcp`).
2. פותחים PowerShell בתיקייה ומריצים (עם הגרסה שלכם):
   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\install.ps1 -RevitVersion 2025
   ```
3. מעתיקים את קטע ה-JSON שהסקריפט מדפיס לקובץ `%APPDATA%\Claude\claude_desktop_config.json`, ומפעילים מחדש את Claude Desktop.
4. פותחים את Revit ובוחרים **Always Load** עבור "Revit MCP Bridge".

בדיקה: כשהמודל פתוח, נכנסים בדפדפן ל-`http://127.0.0.1:8765/ping`. אמור להופיע `{"ok":true}`.

## מה Claude יכול לעשות

| כלי | מה הוא עושה |
|---|---|
| `get_model_info` | שם המודל, מפלסים, כמות אלמנטים |
| `list_levels`, `list_views`, `set_active_view` | מפלסים ומבטים |
| `list_elements`, `list_types`, `get_element` | רשימת אלמנטים, סוגים וכל הפרמטרים |
| `get_selection`, `select_elements` | מה שמסומן עכשיו, וסימון וזום לאלמנטים |
| `get_quantities` | כתב כמויות לפי סוג: נפח בטון (מ"ק), שטח, אורך |
| `set_parameter` | שינוי פרמטר של אלמנט או של סוג |
| `create_level`, `create_wall`, `create_floor` | יצירת מפלס, קיר ותקרה |
| `place_column`, `create_beam` | הצבת עמודים (כמה בבת אחת) וקורות |
| `move_elements`, `delete_elements` | הזזה ומחיקה |

כל המידות במטרים. כל פעולה נרשמת כ-Transaction בשם "MCP: …", כך שאפשר לבטל אותה ב-Revit עם Ctrl+Z.

### דוגמאות לבקשות

- "כמה מ"ק בטון יש בתקרות ובעמודים בקומה 2?"
- "צור רשת עמודים 40x40 כל 6 מטר, 4 על 3, מקומה 1 עד קומה 2"
- "תחליף את Comments לכל הקירות בקומה 1 ל-'שלב א'"
- "צור תקרה 12x18 מטר במפלס Level 2"

## הערות

- השרת מאזין רק ל-`127.0.0.1`, כך שאי אפשר להתחבר אליו ממחשב אחר.
- אם פתוח חלון דו-שיח ב-Revit, הפקודה תמתין עד שייסגר.
- כדי להציב עמוד או קורה, המשפחה צריכה להיות טעונה בפרויקט.
- פורט אחר: משתנה הסביבה `REVIT_MCP_PORT` (בצד של Revit) ו-`REVIT_MCP_URL` (בצד של שרת ה-MCP).
- **שליטה מרחוק** (מטלפון או ממחשב אחר): הכי פשוט להתחבר למחשב עם Claude Desktop פתוח, או להשתמש ב-Remote Control של Claude Code על אותו מחשב.
