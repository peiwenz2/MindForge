# MindForge 🔥

**Your Extended Mind - Never Sleeps, Never Tires, Always Thinking**

## Vision

MindForge is your personal thinking partner - an AI agent that takes your questions and insights, then researches, learns, thinks, and iterates autonomously until reaching convergence.

> "A second mind with access to all knowledge, working on your questions while you focus on what matters."

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  YOU: Submit Question/Insight                               │
│  "How does EBS relate to AI growth?"                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  MINDFORGE: Autonomous Thinking Cycle                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Cycle 1: Research → Think → Generate Questions      │   │
│  │ Cycle 2: Research → Think → Generate Questions      │   │
│  │ Cycle 3: Research → Think → Generate Questions      │   │
│  │ ...                                                  │   │
│  │ Cycle N: Review → No New Questions → CONVERGENCE    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  OUTPUT: Converged Insights + Thinking Path                 │
│  - Final answer with evidence                               │
│  - Complete reasoning trail                                 │
│  - Sources and references                                   │
└─────────────────────────────────────────────────────────────┘
```

## Core Features

### 🧠 Iterative Thinking
- Each cycle: Research → Think → Self-Question → Learn
- Configurable cycle interval (default: 60 seconds)
- Automatic convergence detection

### 📚 Dynamic Skill Installation
- Auto-installs needed skills for research
- Currently supports: web search, stock analysis, news, weather
- Extensible skill marketplace

### 🛡️ Self-Healing
- Watchdog monitors and auto-restarts
- Crash recovery with state preservation
- GitHub sync for backup

### 💾 Memory Management
- Configurable memory limits
- Thinking path tracking
- Question/insight history

## Quick Start

### 1. Submit a Question

Create/edit `memory/current-question.md`:

```markdown
# Question: How does elastic block storage relate to AI growth?

**Submitted**: 2026-03-10 15:30
**Priority**: High
**Context**: 
- Working on cloud storage strategy
- AI industry booming, need to understand storage implications
- Want to know how EBS products can maintain leadership

**Desired Output**:
- Market analysis
- Technical requirements
- Strategic recommendations
```

### 2. Start MindForge

```bash
cd /home/admin/.openclaw/workspace/mindforge
bash watchdog.sh
```

### 3. Monitor Progress

```bash
# View current thinking state
cat memory/current-state.md

# View thinking path
cat memory/thinking-path.md

# View logs
tail -f logs/mindforge.log
```

### 4. Check Convergence

When MindForge reaches convergence:
- No new questions generated after review
- Switches model for final review
- Marks question as "CONVERGED"
- You receive notification

## Configuration

Edit `config.json`:

```json
{
  "cycleIntervalSeconds": 60,
  "maxMemoryMB": 500,
  "autoConvergence": true,
  "reviewCyclesBeforeConvergence": 2,
  "modelForThinking": "qwen3.5-plus",
  "modelForReview": "glm-5",
  "githubSync": true,
  "githubSyncInterval": 60
}
```

## File Structure

```
mindforge/
├── README.md           # This file
├── MISSION.md          # Project mission and goals
├── config.json         # Configuration
├── convergence.py      # Main thinking engine
├── thinker.py          # Thinking/reasoning logic
├── researcher.py       # Research/data fetching
├── memory/
│   ├── current-question.md   # Active question
│   ├── current-state.md      # Current thinking state
│   ├── thinking-path.md      # Complete reasoning trail
│   ├── questions.json        # Question history
│   └── insights.json         # Converged insights
├── logs/
│   ├── mindforge.log         # Main logs
│   └── watchdog.log          # Watchdog logs
├── skills/                   # Installed skills
├── watchdog.sh               # Auto-restart daemon
└── sync-github.sh            # GitHub backup
```

## Convergence Detection

MindForge knows when to stop:

1. **Primary Review**: Current cycle generates no new questions
2. **Secondary Review**: Switch model, review again
3. **Convergence**: If still no questions → Stop and deliver results

This ensures thorough exploration without infinite loops.

## Example Output

After convergence, `memory/insights.json`:

```json
{
  "question": "How does EBS relate to AI growth?",
  "status": "CONVERGED",
  "cycles": 47,
  "duration": "47 minutes",
  "summary": "EBS is critical infrastructure for AI workloads...",
  "keyInsights": [
    "AI training requires high-throughput storage...",
    "EBS providers must support NVMe over Fabrics...",
    "Market opportunity: $X billion by 2028..."
  ],
  "sources": [...],
  "thinkingPath": "memory/thinking-path.md"
}
```

## Philosophy

MindForge embodies:
- **Persistence**: Never gives up on a question
- **Rigor**: Reviews and validates thinking
- **Efficiency**: Works while you focus on other things
- **Transparency**: Complete thinking trail visible

---

**Created**: 2026-03-10
**Inspired by**: The need for a thinking partner in a busy world
