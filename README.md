# 👾LaRue.exe — DEV

<!-- Badges principaux -->
![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![discord.py](https://img.shields.io/badge/discord.py-app__commands-green)
![DB](https://img.shields.io/badge/SQLite-WAL-lightgrey)
![Platform](https://img.shields.io/badge/Env-DEV-orange)

<!-- Badges GitHub (dynamiques) -->
![Last commit](https://img.shields.io/github/last-commit/<owner>/<repo>/dev)
![Commits (dev)](https://img.shields.io/github/commit-activity/m/<owner>/<repo>)
![Issues](https://img.shields.io/github/issues/<owner>/<repo>

Ce dépôt correspond à la branche **dev** (environnement de test).  
Voici l’arborescence actuelle (générée depuis `tree.txt`) :

```text
.
├── bot
│   ├── __init__.py
│   ├── __main__.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── config.py
│   │   ├── db
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── migrations
│   │   │       ├── __init__.py
│   │   │       ├── v0001_base.py
│   │   │       ├── v0002_recycler.py
│   │   │       ├── v0003_idx.py
│   │   │       └── v0004_ledger.py
│   │   ├── storage.py
│   │   └── utils.py
│   ├── domain
│   │   ├── __init__.py
│   │   ├── clock.py
│   │   ├── economy.py
│   │   └── quotas.py
│   ├── modules
│   │   ├── __init__.py
│   │   ├── admin
│   │   │   ├── __init__.py
│   │   │   └── admin.py
│   │   ├── common
│   │   │   ├── __init__.py
│   │   │   ├── checks.py
│   │   │   ├── money.py
│   │   │   └── ui.py
│   │   ├── rp
│   │   │   ├── __init__.py
│   │   │   ├── betting.py
│   │   │   ├── boosts.py
│   │   │   ├── combat.py
│   │   │   ├── economy.py
│   │   │   ├── items.py
│   │   │   ├── profile.py
│   │   │   ├── recycler.py
│   │   │   ├── shop.py
│   │   │   ├── start.py
│   │   │   └── tabac.py
│   │   ├── social
│   │   │   ├── __init__.py
│   │   │   └── profile.py
│   │   └── system
│   │       ├── __init__.py
│   │       ├── health.py
│   │       └── sysinfo.py
│   └── persistence
│       ├── __init__.py
│       ├── actions.py
│       ├── inventory.py
│       ├── ledger.py
│       ├── players.py
│       ├── profiles.py
│       ├── recycler.py
│       ├── respect.py
│       └── stats.py
├── data
├── requirements.txt
└── tree.txt

14 directories, 52 files