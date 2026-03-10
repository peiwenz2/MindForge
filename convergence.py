#!/usr/bin/env python3
"""
MindForge - Convergence Engine
Main thinking loop: Research → Think → Self-Question → Iterate
"""

import os
import sys
import time
import json
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

WORKSPACE = Path("/home/admin/.openclaw/workspace/mindforge")
CONFIG_FILE = WORKSPACE / "config.json"
QUESTION_FILE = WORKSPACE / "memory" / "current-question.md"
STATE_FILE = WORKSPACE / "memory" / "current-state.md"
THINKING_PATH_FILE = WORKSPACE / "memory" / "thinking-path.md"
QUESTIONS_FILE = WORKSPACE / "memory" / "questions.json"
INSIGHTS_FILE = WORKSPACE / "memory" / "insights.json"
LOG_FILE = WORKSPACE / "logs" / "mindforge.log"

# Force unbuffered output
sys.stdout = open(sys.stdout.fileno(), 'w', buffering=1, encoding=sys.stdout.encoding)
sys.stderr = open(sys.stderr.fileno(), 'w', buffering=1, encoding=sys.stderr.encoding)

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except:
        pass

def load_config():
    """Load configuration"""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {
        "cycleIntervalSeconds": 60,
        "maxMemoryMB": 500,
        "autoConvergence": True,
        "reviewCyclesBeforeConvergence": 2,
        "maxCyclesPerQuestion": 500
    }

def read_question():
    """Read current question from file"""
    if QUESTION_FILE.exists():
        content = QUESTION_FILE.read_text()
        # Extract question title
        for line in content.split('\n'):
            if line.startswith('# Question:'):
                return line.replace('# Question:', '').strip()
        return content[:200]
    return None

def read_state():
    """Read current thinking state"""
    if STATE_FILE.exists():
        return STATE_FILE.read_text()
    return ""

def write_state(content):
    """Write thinking state"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(content)

def read_thinking_path():
    """Read complete thinking path"""
    if THINKING_PATH_FILE.exists():
        return THINKING_PATH_FILE.read_text()
    return "# Thinking Path\n\n"

def append_thinking_path(entry):
    """Append to thinking path"""
    THINKING_PATH_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(THINKING_PATH_FILE, "a") as f:
        f.write(f"\n--- {timestamp} ---\n{entry}\n")

def read_questions():
    """Read question history"""
    if QUESTIONS_FILE.exists():
        try:
            return json.loads(QUESTIONS_FILE.read_text())
        except:
            pass
    return {"original": "", "generated": [], "answered": [], "cycle": 0}

def write_questions(data):
    """Write question history"""
    QUESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUESTIONS_FILE.write_text(json.dumps(data, indent=2))

def read_insights():
    """Read converged insights"""
    if INSIGHTS_FILE.exists():
        try:
            return json.loads(INSIGHTS_FILE.read_text())
        except:
            pass
    return []

def write_insight(insight):
    """Write converged insight"""
    insights = read_insights()
    insights.append(insight)
    INSIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSIGHTS_FILE.write_text(json.dumps(insights, indent=2, ensure_ascii=False))

def get_folder_size_mb():
    """Get workspace size in MB"""
    try:
        result = subprocess.run(
            ["du", "-sb", str(WORKSPACE)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True
        )
        return int(result.stdout.split()[0]) / (1024 * 1024)
    except:
        return 0

def web_search(query, count=5):
    """Search the web using DuckDuckGo HTML interface"""
    try:
        log(f"  🔍 Searching: {query[:60]}...")
        import urllib.parse
        safe_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={safe_query}"
        
        cmd = f'curl -s -A "Mozilla/5.0" --max-time 15 "{url}" 2>/dev/null | grep -oP "<a[^>]*href=\\"\\K[^\\"]*" | head -{count}'
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=20)
        
        if result.returncode == 0 and result.stdout:
            urls = [u for u in result.stdout.strip().split('\n') if u and 'duckduckgo' not in u][:count]
            # Fetch content from first URL
            if urls:
                content_cmd = f'curl -s -A "Mozilla/5.0" --max-time 10 "{urls[0]}" 2>/dev/null | head -3000'
                content_result = subprocess.run(content_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
                if content_result.stdout:
                    return [{'title': query, 'url': urls[0], 'snippet': content_result.stdout[:500]}]
        return []
    except Exception as e:
        log(f"  ⚠️  Search error: {str(e)[:80]}")
        return []

def think_and_generate_questions(question, context, research_results, current_questions):
    """
    Use AI to think about the question and generate new questions
    Returns: (insights, new_questions, should_continue)
    """
    try:
        # Build prompt for thinking - AI has built-in knowledge
        research_summary = "\n".join([
            f"- {r.get('title', 'N/A')[:100]}: {r.get('snippet', '')[:200]}"
            for r in research_results[:3]
        ]) if research_results else "(Will use internal knowledge)"
        
        recent_questions = "\n".join([
            f"- {q}" for q in current_questions[-10:]
        ]) if current_questions else "None yet"
        
        prompt = f"""You are MindForge, an autonomous thinking agent exploring deep questions.

**Original Question**: {question}

**Research Found**:
{research_summary}

**Previous Questions Explored**:
{recent_questions}

**Your Task**:
1. Use your knowledge to think deeply about this question
2. Generate 1-3 NEW questions that would deepen understanding
3. Provide concrete insights based on your knowledge

**Think about**:
- Technical aspects
- Market dynamics  
- Future trends
- Practical implications

**Format your response EXACTLY as**:
INSIGHTS:
- [insight 1]
- [insight 2]
...

NEW QUESTIONS:
- [question 1]
- [question 2]
...

CONVERGENCE: [YES if no meaningful new questions, NO if more exploration needed]
"""
        
        # Call AI model for thinking
        safe_prompt = prompt.replace('\n', ' ').replace('"', '\\"')
        cmd = f'openclaw message --message "{safe_prompt}" 2>/dev/null'
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
        
        # Parse response
        response = result.stdout if result.returncode == 0 else ""
        
        insights = []
        new_questions = []
        convergence = False
        
        if "INSIGHTS:" in response:
            insights_section = response.split("INSIGHTS:")[1].split("NEW QUESTIONS:")[0] if "NEW QUESTIONS:" in response else response.split("INSIGHTS:")[1]
            for line in insights_section.strip().split('\n'):
                if line.strip().startswith('-'):
                    insights.append(line.strip()[1:].strip())
        
        if "NEW QUESTIONS:" in response:
            questions_section = response.split("NEW QUESTIONS:")[1].split("CONVERGENCE:")[0] if "CONVERGENCE:" in response else response.split("NEW QUESTIONS:")[1]
            for line in questions_section.strip().split('\n'):
                if line.strip().startswith('-'):
                    new_questions.append(line.strip()[1:].strip())
        
        if "CONVERGENCE: YES" in response:
            convergence = True
        
        return insights, new_questions, not convergence
        
    except Exception as e:
        log(f"  ⚠️  Thinking error: {str(e)[:100]}")
        return [], [], True

def review_for_convergence(question, thinking_path, insights):
    """
    Review complete thinking path to check if converged
    Returns: (is_converged, final_summary)
    """
    try:
        prompt = f"""You are reviewing a thinking session for convergence.

**Original Question**: {question}

**Thinking Path Summary**: {thinking_path[-2000:]}

**Key Insights**: {'; '.join(insights[-10:]) if insights else 'None'}

**Task**: Determine if thinking has converged (no meaningful new questions possible).

**Respond with**:
CONVERGED: YES or NO
SUMMARY: [Brief summary of final understanding]
REASONING: [Why converged or what's missing]
"""
        
        safe_prompt = prompt.replace('\n', ' ').replace('"', '\\"')
        cmd = f'openclaw message --message "{safe_prompt}" 2>/dev/null'
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=60)
        
        response = result.stdout if result.returncode == 0 else ""
        
        converged = "CONVERGED: YES" in response
        summary = ""
        if "SUMMARY:" in response:
            summary = response.split("SUMMARY:")[1].split("REASONING:")[0].strip() if "REASONING:" in response else response.split("SUMMARY:")[1].strip()
        
        return converged, summary
        
    except Exception as e:
        log(f"  ⚠️  Review error: {str(e)[:100]}")
        return False, ""

def run_thinking_cycle(cycle_num, config):
    """Execute one thinking cycle"""
    log(f"\n{'='*60}")
    log(f"[CYCLE {cycle_num}] Starting at {datetime.now().strftime('%H:%M:%S')}")
    
    # Read current state
    question = read_question()
    if not question:
        log("⚠️  No question loaded. Waiting for user to submit one.")
        return cycle_num, False
    
    state = read_state()
    questions_data = read_questions()
    thinking_path = read_thinking_path()
    
    # Get recent questions to explore
    recent_questions = questions_data.get('generated', [])[-10:]
    answered = questions_data.get('answered', [])
    
    # Pick next question to explore
    if recent_questions:
        current_focus = recent_questions[0]
    else:
        current_focus = question
        questions_data['generated'].append(question)
    
    log(f"📍 Focus: {current_focus[:80]}...")
    
    # Research
    research_results = web_search(current_focus, count=5)
    log(f"  📚 Found {len(research_results)} sources")
    
    # Think and generate new questions
    insights, new_questions, should_continue = think_and_generate_questions(
        question, state, research_results, questions_data['generated']
    )
    
    log(f"  💡 Generated {len(insights)} insights, {len(new_questions)} new questions")
    
    # Update state
    if insights:
        for insight in insights:
            questions_data['answered'].append(insight)
    
    if new_questions:
        questions_data['generated'].extend(new_questions)
        for q in new_questions:
            append_thinking_path(f"NEW QUESTION: {q}")
    
    # Update thinking path
    cycle_entry = f"""
## Cycle {cycle_num}
**Focus**: {current_focus[:100]}
**Research**: {len(research_results)} sources
**Insights**: {len(insights)}
**New Questions**: {len(new_questions)}
"""
    append_thinking_path(cycle_entry)
    
    # Check convergence
    convergence_count = 0
    if not new_questions and config.get('autoConvergence', True):
        convergence_count += 1
        log(f"  🔄 No new questions - convergence review #{convergence_count}")
        
        if convergence_count >= config.get('reviewCyclesBeforeConvergence', 2):
            # Final review
            log("  ✨ Final convergence review...")
            is_converged, summary = review_for_convergence(
                question, thinking_path + cycle_entry, insights
            )
            
            if is_converged:
                log("  🎯 CONVERGENCE REACHED!")
                
                # Save final insight
                final_insight = {
                    "question": question,
                    "status": "CONVERGED",
                    "cycles": cycle_num,
                    "converged_at": datetime.now().isoformat(),
                    "summary": summary,
                    "insights": insights,
                    "thinking_path": "memory/thinking-path.md"
                }
                write_insight(final_insight)
                
                # Update state
                new_state = f"""# MindForge - CONVERGED

**Question**: {question}
**Status**: ✅ CONVERGED
**Cycles**: {cycle_num}
**Completed**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
{summary}

## Key Insights
{chr(10).join(['- ' + i for i in insights])}

## Thinking Path
See memory/thinking-path.md for complete reasoning trail.
"""
                write_state(new_state)
                write_questions(questions_data)
                
                return cycle_num, True  # Signal convergence
    
    # Update state for next cycle
    mem_size = get_folder_size_mb()
    new_state = f"""# MindForge - Active Thinking

**Question**: {question}
**Status**: 🔄 THINKING
**Cycle**: {cycle_num}
**Last Update**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Current Focus
{current_focus[:200]}

## Progress
- Questions Generated: {len(questions_data['generated'])}
- Insights Collected: {len(questions_data['answered'])}
- Convergence Reviews: {convergence_count}

## Memory
- Size: {mem_size:.2f}MB
- Limit: {config.get('maxMemoryMB', 500)}MB

## Recent Insights
{chr(10).join(['- ' + i[:100] for i in insights[-5:]]) if insights else 'None yet'}
"""
    write_state(new_state)
    write_questions(questions_data)
    
    log(f"[CYCLE {cycle_num}] Complete. Memory: {mem_size:.2f}MB")
    
    return cycle_num + 1, False

def main():
    """Main loop"""
    config = load_config()
    
    log("="*60)
    log("🔥 MindForge v1.0 - Extended Mind Engine")
    log(f"📊 Cycle interval: {config.get('cycleIntervalSeconds', 60)}s")
    log(f"💾 Max memory: {config.get('maxMemoryMB', 500)}MB")
    log(f"🎯 Auto-convergence: {config.get('autoConvergence', True)}")
    log("="*60)
    
    cycle_num = 1
    converged = False
    
    while not converged:
        try:
            cycle_num, converged = run_thinking_cycle(cycle_num, config)
            
            if not converged:
                interval = config.get('cycleIntervalSeconds', 60)
                log(f"[WAIT] Sleeping {interval} seconds...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            log("\n🛑 Interrupted by user")
            break
        except Exception as e:
            log(f"❌ ERROR: {e}")
            traceback.print_exc(file=sys.stderr, flush=True)
            time.sleep(10)
    
    log("\n✨ Session complete!")

if __name__ == "__main__":
    main()
