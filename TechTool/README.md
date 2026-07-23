# Tech Tool

Tech Tool is a Windows desktop application used by the Package Library team to streamline package review, QA, and repository maintenance.

The application provides a centralized interface for inspecting package information, reviewing reports, and performing common package operations while maintaining audit history and reducing repetitive manual work.

## Owners

This project is maintained by the Package Library team.

- Chad
- Casey
- Tamas

For questions, bug reports, or feature requests, please contact one of the maintainers or create a GitHub issue.

---

## Highlights

- Browse and search the Package Library repository
- Review package status and QA information
- Perform package maintenance through a unified interface
- Record actions in package audit logs
- AI-assisted workflows for selected tasks
- Modular action framework designed for future expansion

---

## Architecture

The project is organized to keep the user interface separate from package logic.

| File | Responsibility |
|------|----------------|
| **TechTool.py** | User interface, navigation, and application state |
| **actions.py** | Reusable package operations and business logic |
| **ai.py** | Shared AI communication layer |

Keeping business logic independent of the UI allows the same actions to be reused by future interfaces without duplication.

---

## Design Goals

- Keep package actions modular and reusable
- Separate UI from business logic
- Provide clear audit history for repository changes
- Minimize repetitive Package Library tasks
- Build a foundation for future desktop and web tooling

---

## AI Features

Several actions can use AI to generate recommendations or assist with repetitive work.

AI-generated content is always presented for user review before being saved or applied.

---

## Requirements

- Windows
- Python 3.14+
- Tkinter
- Access to the Package Library repository
- OpenAI API key (optional, for AI-assisted features)

---

## Running

```powershell
python .\TechTool.py
```

---

## Contributing

When adding new features:

- Keep UI code inside `TechTool.py`
- Keep reusable logic inside `actions.py`
- Keep AI transport inside `ai.py`
- Audit any action that modifies package state
- Favor reusable actions over UI-specific implementations

---

## Future Direction

Tech Tool is being designed as the foundation for a broader Package Operations platform.

Future goals include:
- Shared package action library
- Web-based Package Operations Dashboard
- Central package database
- Additional AI-assisted package analysis and repair
- Expanded automation tooling