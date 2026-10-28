import marimo

__generated_with = "0.25.1"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Memory Benchmarks (LoCoMo & LongMemEval)

    > **You can't improve what you can't measure. LoCoMo and LongMemEval provide standardized test suites that reveal exactly where your memory system fails: single-hop recall, multi-hop reasoning, temporal ordering, or open-ended generation.**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Motivation

    Imagine you hire a new assistant and give them a quiz after their first week. One section tests whether they remember your coffee order (direct recall). Another checks if they can connect two separate conversations to plan your schedule (multi-hop reasoning). A third tests whether they know you switched from tea to coffee last Wednesday (temporal awareness). Your overall score is useful, but the per-section breakdown tells you exactly what to train.

    **LoCoMo** (Long-Context Conversational Memory) and **LongMemEval** are standardized benchmarks that work the same way for AI memory systems. They provide multi-session conversations paired with ground-truth questions. Each question targets a specific memory capability. Running your system against these benchmarks produces per-category scores that turn "memory quality" from a vague claim into a concrete number you can track and improve.

    Every agent memory system claims to "remember" conversations. But can it recall a preference mentioned 50 messages ago? Can it connect facts from two different sessions? Does it know which of two contradictory statements came last? Without benchmarks, you're guessing. With them, you know.

    **In this notebook you will:**
    1. Load the LoCoMo benchmark dataset and explore its structure.
    2. Build a memory system adapter that ingests benchmark conversations.
    3. Run a prediction pipeline that answers benchmark questions using retrieved context.
    4. Score predictions with BLEU, ROUGE-L, F1, and an LLM judge.
    5. Analyze per-category results and compare against a no-memory baseline.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Key Concepts

    - **LoCoMo benchmark**: A dataset of 10 multi-session conversations with about 2,000 question-answer pairs. Each conversation simulates two people chatting across up to 35 sessions. The questions test five categories of memory capability. "Benchmark" means a standardized test you run to measure performance.
    - **LongMemEval**: A complementary benchmark with 500 question-answer instances. Each instance is a user-assistant chat history spanning 40 to 500 sessions. It tests five core memory abilities including abstention (knowing when information was never mentioned). "Abstention" means the system correctly refuses to answer instead of guessing.
    - **Single-hop question**: A question that requires retrieving one fact from one session. Example: "What is Caroline's favorite color?" The answer appears in a single dialogue turn.
    - **Multi-hop question**: A question that requires connecting facts from two or more sessions. Example: "Which of Caroline's colleagues also attended the conference she mentioned?" You need information from at least two different conversations.
    - **Temporal question**: A question about when something happened or what changed over time. Example: "What was the user's job before they switched careers?" The system must understand ordering and timestamps.
    - **Open-ended question**: A question requiring a synthesized answer from facts scattered across sessions. There's no single correct phrase. The answer must be coherent and complete.
    - **Adversarial question**: A question designed to mislead. It may reference events that never happened or contradict the conversation. A good memory system should recognize the trap.
    - **BLEU score**: A metric (a number between 0 and 1) that measures how many word sequences in the predicted answer match the reference answer. Higher means more overlap. "N-gram" means a sequence of N consecutive words.
    - **ROUGE-L score**: A metric that measures the longest common subsequence between prediction and reference. It focuses on recall (how much of the reference was captured). "Subsequence" means words that appear in order but not necessarily next to each other.
    - **F1 score**: A metric that balances precision (what fraction of predicted words are correct) and recall (what fraction of reference words were predicted). It's the harmonic mean of the two.
    - **LLM judge**: Using a capable model (like GPT-4 or Claude) to grade whether a free-form answer is correct. This handles cases where the wording differs but the meaning matches.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Architecture

    <p align="center">
      <img src="../../images/diagrams/29_memory_benchmarks_LoCoMo.svg" alt="diagram" width="720"/>
    </p>

    The diagram shows the full evaluation workflow. Benchmark data (conversations, questions, and ground-truth answers) feeds into your memory system under test. The system ingests conversations, then answers each question using its retrieval mechanism. Predictions flow into the scoring pipeline, which computes BLEU, ROUGE, F1, and LLM-judge scores. The results break down into per-category scores, weakness analysis, and baseline comparisons.

    The key insight: you test your system the same way you'd test it in production, but with known-correct answers. This lets you measure improvement as you iterate on your memory architecture.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Setup

    Install the required packages. We use `datasets` to load LoCoMo from HuggingFace, `rouge-score` and `nltk` for text metrics, and `openai` for the LLM calls and LLM-judge scoring.
    """)
    return


@app.cell
def _():
    # '%pip install -q openai python-dotenv datasets rouge-score nltk' command supported automatically in marimo
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Import all dependencies and configure API access. You need an `OPENAI_API_KEY` environment variable set.
    """)
    return


@app.cell
def _():
    import os
    import json
    import re
    import collections
    from dotenv import load_dotenv

    load_dotenv()

    import openai
    import nltk
    from datasets import load_dataset
    from rouge_score import rouge_scorer

    # Download NLTK data for BLEU scoring
    nltk.download("punkt", quiet=True)
    nltk.download("punkt_tab", quiet=True)

    client = openai.OpenAI()

    assert os.getenv("OPENAI_API_KEY"), "Set OPENAI_API_KEY in your .env file"

    MODEL = "gpt-4o-mini"
    JUDGE_MODEL = "gpt-4o-mini"
    return (
        JUDGE_MODEL,
        MODEL,
        client,
        collections,
        json,
        load_dataset,
        rouge_scorer,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Implementation

    ### Step 1: Load and Explore the LoCoMo Dataset

    LoCoMo is hosted on HuggingFace. Each sample contains a multi-session conversation between two speakers, plus question-answer pairs organized by category. Let's load one sample and inspect its structure.
    """)
    return


@app.cell
def _(load_dataset):
    # Load the LoCoMo dataset from HuggingFace
    locomo_dataset = load_dataset("snap-stanford/LoCoMo", split="train")

    print(f"Number of conversation samples: {len(locomo_dataset)}")
    print(f"Fields per sample: {list(locomo_dataset[0].keys())}")
    return (locomo_dataset,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Let's examine one conversation sample. Each sample has sessions (numbered dialogue exchanges), a set of QA pairs, and supporting metadata like event summaries.
    """)
    return


@app.cell
def _(json, locomo_dataset):
    # Pick the first conversation sample
    sample = locomo_dataset[0]

    # Parse the conversation JSON
    conversation = json.loads(sample["conversation"])

    print(f"Speaker A: {conversation['speaker_a']}")
    print(f"Speaker B: {conversation['speaker_b']}")

    # Count sessions by looking for session keys
    session_keys = sorted([k for k in conversation if k.startswith("session_") and not k.endswith("_date_time")])
    print(f"Number of sessions: {len(session_keys)}")

    # Show first session's first few turns
    first_session = conversation[session_keys[0]]
    print(f"\nFirst session has {len(first_session)} turns:")
    for turn in first_session[:3]:
        speaker = turn["speaker"]
        text = turn["text"][:100] + ("..." if len(turn["text"]) > 100 else "")
        print(f"  {speaker}: {text}")
    return (sample,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now let's look at the question-answer pairs. Each QA has a category (1-5), a question, a ground-truth answer, and evidence pointers back to specific dialogue turns.
    """)
    return


@app.cell
def _(collections, json, sample):
    # Parse the QA pairs
    qa_pairs = json.loads(sample['qa'])
    CATEGORY_NAMES = {1: 'single-hop', 2: 'temporal', 3: 'multi-hop', 4: 'open-ended', 5: 'adversarial'}
    # Category mapping
    category_counts = collections.Counter((q['category'] for q in qa_pairs))
    print('Question counts by category:')
    for _cat_id in sorted(category_counts):
        _name = CATEGORY_NAMES.get(_cat_id, f'unknown-{_cat_id}')
        print(f'  Category {_cat_id} ({_name}): {category_counts[_cat_id]}')
    print(f'\nTotal QA pairs in this sample: {len(qa_pairs)}')
    print('\n--- Example questions ---')
    shown = set()
    # Count questions by category
    for _q in qa_pairs:
        _cat = _q['category']
        if _cat not in shown:
            shown.add(_cat)
            answer_text = str(_q['answer'])[:80]
            print(f'\n[{CATEGORY_NAMES.get(_cat, _cat)}]')
            print(f"  Q: {_q['question']}")
            print(f'  A: {answer_text}')
    # Show examples from each category
            print(f"  Evidence: {_q.get('evidence', 'N/A')}")
    return CATEGORY_NAMES, qa_pairs


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 2: Build Conversation Context

    Before we can answer questions, we need to convert the structured dialogue into a flat text format. This simulates what a memory system would store and retrieve. We'll build the full conversation text with session markers and timestamps.
    """)
    return


@app.cell
def _(json, sample):
    def build_conversation_text(conversation_json):
        """Convert a LoCoMo conversation dict into a flat text with session markers."""
        conversation = json.loads(conversation_json) if isinstance(conversation_json, str) else conversation_json

        session_keys = sorted(
            [k for k in conversation if k.startswith("session_") and not k.endswith("_date_time")],
            key=lambda k: int(k.split("_")[1])
        )

        parts = []
        for session_key in session_keys:
            session_num = session_key.split("_")[1]
            date_key = f"{session_key}_date_time"
            timestamp = conversation.get(date_key, "unknown date")

            parts.append(f"\n=== Session {session_num} ({timestamp}) ===")

            for turn in conversation[session_key]:
                parts.append(f"{turn['speaker']}: {turn['text']}")

        return "\n".join(parts)


    # Build context for our sample
    full_context = build_conversation_text(sample["conversation"])
    print(f"Full conversation length: {len(full_context)} characters")
    print(f"Approximate tokens: ~{len(full_context) // 4}")
    print(f"\nFirst 500 characters:")
    print(full_context[:500])
    return (full_context,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 3: Build the Prediction Pipeline

    For each question, we send the conversation context plus the question to the LLM. The model generates an answer based on what it finds in the context. This is the "full-context baseline" approach: we pass the entire conversation as context.

    In a production memory system, you'd replace this with your retrieval mechanism. The benchmark stays the same. Only the context-selection step changes.
    """)
    return


@app.cell
def _(MODEL, client, full_context, qa_pairs):
    def generate_prediction(question, context, model=MODEL):
        """Generate an answer to a benchmark question given conversation context."""
        system_prompt = (
            "You are answering questions about a conversation history. "
            "Use only the information in the provided conversation. "
            "If the answer is not in the conversation, say 'I don't know'. "
            "Keep your answer brief and direct (1-2 sentences max)."
        )

        user_prompt = (
            f"Conversation history:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer based only on the conversation above:"
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=256,
            temperature=0.0,
        )

        return response.choices[0].message.content.strip()


    # Test with one question
    test_q = qa_pairs[0]
    test_answer = generate_prediction(test_q["question"], full_context)
    print(f"Question:   {test_q['question']}")
    print(f"Predicted:  {test_answer}")
    print(f"Reference:  {test_q['answer']}")
    return (generate_prediction,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now let's run predictions for a subset of questions. We'll limit to 30 questions (sampled across categories) to keep API costs low. In a full evaluation, you'd run all questions.
    """)
    return


@app.cell
def _(
    CATEGORY_NAMES,
    collections,
    full_context,
    generate_prediction,
    qa_pairs,
):
    import random
    random.seed(42)
    scorable_qs = [q for q in qa_pairs if q['category'] in [1, 2, 3, 4]]
    sample_size = min(30, len(scorable_qs))
    # Sample up to 30 questions, stratified across categories 1-4
    # (Category 5 is adversarial and typically excluded from scoring)
    sampled_qs = random.sample(scorable_qs, sample_size)
    print(f'Running predictions for {sample_size} questions...')
    category_sample_counts = collections.Counter((q['category'] for q in sampled_qs))
    for _cat_id in sorted(category_sample_counts):
        print(f'  {CATEGORY_NAMES[_cat_id]}: {category_sample_counts[_cat_id]}')
    predictions = []
    for _i, _q in enumerate(sampled_qs):
        _pred = generate_prediction(_q['question'], full_context)
        predictions.append({'question': _q['question'], 'prediction': _pred, 'reference': str(_q['answer']), 'category': _q['category'], 'evidence': _q.get('evidence', [])})
        if (_i + 1) % 10 == 0:
            print(f'  Completed {_i + 1}/{sample_size}')
    print(f'\nAll {sample_size} predictions generated.')
    return predictions, sample_size, sampled_qs


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 4: Build the Scoring Pipeline

    We'll compute three automated metrics for each prediction:

    1. **BLEU-1**: Unigram overlap between prediction and reference.
    2. **ROUGE-L**: Longest common subsequence overlap.
    3. **Token F1**: Precision and recall at the word level.

    These metrics each capture a different aspect of answer quality. BLEU emphasizes precision (are the predicted words correct?). ROUGE emphasizes recall (are the reference words covered?). F1 balances both.
    """)
    return


@app.cell
def _(collections, predictions, rouge_scorer):
    def compute_token_f1(prediction, reference):
        """Compute token-level F1 between prediction and reference strings."""
        pred_tokens = prediction.lower().split()
        ref_tokens = reference.lower().split()

        if not pred_tokens or not ref_tokens:
            return 0.0

        common = collections.Counter(pred_tokens) & collections.Counter(ref_tokens)
        num_common = sum(common.values())

        if num_common == 0:
            return 0.0

        precision = num_common / len(pred_tokens)
        recall = num_common / len(ref_tokens)
        f1 = 2 * precision * recall / (precision + recall)
        return f1


    def compute_bleu1(prediction, reference):
        """Compute BLEU-1 (unigram precision) score."""
        pred_tokens = prediction.lower().split()
        ref_tokens = reference.lower().split()

        if not pred_tokens or not ref_tokens:
            return 0.0

        ref_counts = collections.Counter(ref_tokens)
        clipped = 0
        for token in pred_tokens:
            if ref_counts[token] > 0:
                clipped += 1
                ref_counts[token] -= 1

        return clipped / len(pred_tokens) if pred_tokens else 0.0


    # Initialize ROUGE scorer
    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)


    def compute_rouge_l(prediction, reference):
        """Compute ROUGE-L F-measure."""
        scores = scorer.score(reference, prediction)
        return scores["rougeL"].fmeasure


    # Test metrics on one example
    test_pred = predictions[0]
    print(f"Question:  {test_pred['question']}")
    print(f"Predicted: {test_pred['prediction']}")
    print(f"Reference: {test_pred['reference']}")
    print(f"\nToken F1:  {compute_token_f1(test_pred['prediction'], test_pred['reference']):.3f}")
    print(f"BLEU-1:    {compute_bleu1(test_pred['prediction'], test_pred['reference']):.3f}")
    print(f"ROUGE-L:   {compute_rouge_l(test_pred['prediction'], test_pred['reference']):.3f}")
    return compute_bleu1, compute_rouge_l, compute_token_f1


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 5: LLM Judge Scoring

    Automated text metrics miss cases where the wording differs but the meaning is correct. For example, "New York City" and "NYC" have low token overlap but identical meaning. An LLM judge can assess semantic correctness.

    We ask a capable model to decide: "Is this prediction correct given the reference answer?" The judge returns a binary score (1 for correct, 0 for incorrect).
    """)
    return


@app.cell
def _(JUDGE_MODEL, client, predictions):
    def llm_judge_score(question, prediction, reference, model=JUDGE_MODEL):
        """Use an LLM to judge whether a prediction is semantically correct."""
        prompt = f"You are evaluating an answer to a question about a conversation.\n\nQuestion: {question}\nReference answer: {reference}\nPredicted answer: {prediction}\n\nIs the predicted answer correct? It doesn't need to match word-for-word, but it must convey the same factual information as the reference.\nReply with exactly 'CORRECT' or 'INCORRECT'."
        response = client.chat.completions.create(model=model, messages=[{'role': 'user', 'content': prompt}], max_tokens=16, temperature=0.0)
        reply = response.choices[0].message.content.strip().upper()
        return 1 if 'CORRECT' in reply else 0
    for _p in predictions[:3]:
        _judge = llm_judge_score(_p['question'], _p['prediction'], _p['reference'])
        status = 'CORRECT' if _judge == 1 else 'INCORRECT'
        print(f"Q: {_p['question'][:60]}...")
        print(f"  Pred: {_p['prediction'][:60]}...")
        print(f"  Ref:  {_p['reference'][:60]}...")
    # Test the judge on a few examples
        print(f'  Judge: {status}\n')
    return (llm_judge_score,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 6: Aggregate Scores by Category

    Now we compute all metrics for every prediction and group results by question category. This is where the benchmark's diagnostic power shows up. Per-category scores reveal specific weaknesses.
    """)
    return


@app.cell
def _(
    CATEGORY_NAMES,
    collections,
    compute_bleu1,
    compute_rouge_l,
    compute_token_f1,
    llm_judge_score,
    predictions,
):
    def score_all_predictions(predictions):
        """Score all predictions and return per-category and overall metrics."""
        results_by_category = collections.defaultdict(list)
        for p in predictions:
            f1 = compute_token_f1(p['prediction'], p['reference'])
            bleu = compute_bleu1(p['prediction'], p['reference'])
            rouge = compute_rouge_l(p['prediction'], p['reference'])
            judge = llm_judge_score(p['question'], p['prediction'], p['reference'])
            results_by_category[p['category']].append({'f1': f1, 'bleu1': bleu, 'rougeL': rouge, 'judge': judge})
        summary = {}
        for cat_id, results in sorted(results_by_category.items()):
            n = len(results)
            summary[cat_id] = {'name': CATEGORY_NAMES.get(cat_id, f'cat-{cat_id}'), 'count': n, 'f1': sum((r['f1'] for r in results)) / n, 'bleu1': sum((r['bleu1'] for r in results)) / n, 'rougeL': sum((r['rougeL'] for r in results)) / n, 'judge_accuracy': sum((r['judge'] for r in results)) / n}
        total = sum((s['count'] for s in summary.values()))
        overall = {'name': 'overall', 'count': total, 'f1': sum((s['f1'] * s['count'] for s in summary.values())) / total, 'bleu1': sum((s['bleu1'] * s['count'] for s in summary.values())) / total, 'rougeL': sum((s['rougeL'] * s['count'] for s in summary.values())) / total, 'judge_accuracy': sum((s['judge_accuracy'] * s['count'] for s in summary.values())) / total}
        return (summary, overall)
    print('Scoring all predictions (this calls the LLM judge for each)...')
    category_scores, overall_scores = score_all_predictions(predictions)  # Aggregate per category
    print(f"\n{'Category':<14} {'Count':>5} {'F1':>7} {'BLEU-1':>7} {'ROUGE-L':>8} {'Judge':>7}")
    print('-' * 52)
    for _cat_id, scores in sorted(category_scores.items()):
        print(f"{scores['name']:<14} {scores['count']:>5} {scores['f1']:>7.3f} {scores['bleu1']:>7.3f} {scores['rougeL']:>8.3f} {scores['judge_accuracy']:>7.3f}")
    print('-' * 52)
    # Display results
    print(f"{'overall':<14} {overall_scores['count']:>5} {overall_scores['f1']:>7.3f} {overall_scores['bleu1']:>7.3f} {overall_scores['rougeL']:>8.3f} {overall_scores['judge_accuracy']:>7.3f}")  # Overall (weighted by count)
    return category_scores, overall_scores, score_all_predictions


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Step 7: Compare Against a No-Memory Baseline

    A benchmark score is only meaningful in comparison. Let's build a "no-memory" baseline: the LLM answers each question without any conversation context. This shows how much value the memory system adds.

    If your memory system scores close to the no-memory baseline on some category, your retrieval isn't helping for that question type.
    """)
    return


@app.cell
def _(
    CATEGORY_NAMES,
    MODEL,
    category_scores,
    client,
    overall_scores,
    sample_size,
    sampled_qs,
    score_all_predictions,
):
    def generate_no_memory_prediction(question, model=MODEL):
        """Answer a question with no conversation context (baseline)."""
        response = client.chat.completions.create(model=model, messages=[{'role': 'system', 'content': "Answer the question briefly. If you don't know, say 'I don't know'."}, {'role': 'user', 'content': question}], max_tokens=256, temperature=0.0)
        return response.choices[0].message.content.strip()
    print('Running no-memory baseline...')
    baseline_predictions = []
    for _i, _q in enumerate(sampled_qs):
        _pred = generate_no_memory_prediction(_q['question'])
        baseline_predictions.append({'question': _q['question'], 'prediction': _pred, 'reference': str(_q['answer']), 'category': _q['category']})
        if (_i + 1) % 10 == 0:
            print(f'  Completed {_i + 1}/{sample_size}')
    print('Scoring baseline...')
    baseline_cat_scores, baseline_overall = score_all_predictions(baseline_predictions)
    print(f"\n{'Category':<14} {'Memory Judge':>13} {'No-Memory Judge':>16} {'Delta':>7}")
    # Run no-memory baseline on the same questions
    print('-' * 54)
    for _cat_id in sorted(category_scores):
        mem_score = category_scores[_cat_id]['judge_accuracy']
        base_score = baseline_cat_scores.get(_cat_id, {}).get('judge_accuracy', 0.0)
        delta = mem_score - base_score
        _name = CATEGORY_NAMES.get(_cat_id, f'cat-{_cat_id}')
        print(f'{_name:<14} {mem_score:>13.3f} {base_score:>16.3f} {delta:>+7.3f}')
    print('-' * 54)
    delta_overall = overall_scores['judge_accuracy'] - baseline_overall['judge_accuracy']
    # Side-by-side comparison
    print(f"{'overall':<14} {overall_scores['judge_accuracy']:>13.3f} {baseline_overall['judge_accuracy']:>16.3f} {delta_overall:>+7.3f}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Example Run

    Let's walk through a concrete end-to-end example. We'll pick one question from each category (1-4), show the retrieved context snippet, the prediction, the reference answer, and all metric scores. This makes the evaluation process tangible.
    """)
    return


@app.cell
def _(
    CATEGORY_NAMES,
    compute_bleu1,
    compute_rouge_l,
    compute_token_f1,
    llm_judge_score,
    predictions,
):
    # Pick one question per category for a detailed walkthrough
    print('=' * 70)
    print('DETAILED EXAMPLE: One question per category')
    print('=' * 70)
    shown_cats = set()
    for _p in predictions:
        _cat = _p['category']
        if _cat in shown_cats:
            continue
        shown_cats.add(_cat)
        f1 = compute_token_f1(_p['prediction'], _p['reference'])
        bleu = compute_bleu1(_p['prediction'], _p['reference'])
        rouge = compute_rouge_l(_p['prediction'], _p['reference'])
        _judge = llm_judge_score(_p['question'], _p['prediction'], _p['reference'])
        print(f'\n--- {CATEGORY_NAMES[_cat].upper()} (category {_cat}) ---')
        print(f"Question:  {_p['question']}")
        print(f"Reference: {_p['reference']}")
        print(f"Predicted: {_p['prediction']}")
        print(f"Evidence:  {_p.get('evidence', 'N/A')}")
        print(f"Scores:    F1={f1:.3f}  BLEU-1={bleu:.3f}  ROUGE-L={rouge:.3f}  Judge={('CORRECT' if _judge else 'INCORRECT')}")
        if len(shown_cats) >= 4:
            break
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## LongMemEval: A Complementary Benchmark

    LongMemEval takes a different approach. Instead of friend-to-friend conversations, it uses user-assistant chat histories. Each instance has 40 to 500 sessions and tests seven question types grouped into five memory abilities:

    | Question Type | Memory Ability | What It Tests |
    |---|---|---|
    | single-session-user | Information extraction | Recall facts from user messages in one session |
    | single-session-assistant | Information extraction | Recall facts from assistant messages in one session |
    | single-session-preference | Information extraction | Infer implicit preferences from one session |
    | multi-session | Multi-session reasoning | Connect facts across multiple sessions |
    | knowledge-update | Knowledge updates | Recognize changed information over time |
    | temporal-reasoning | Temporal reasoning | Time-based inference using timestamps |
    | (abstention variants) | Abstention | Correctly refuse when info was never mentioned |

    The evaluation approach is the same: load data, ingest into your memory system, generate predictions, and score. LongMemEval uses an LLM judge (GPT-4o) as its primary metric.

    Here's how you'd load and inspect it:
    """)
    return


@app.cell
def _(collections, load_dataset):
    # Load LongMemEval from HuggingFace
    # The "oracle" split contains only evidence sessions (smallest, good for testing)
    longmemeval = load_dataset("xiaowu0162/longmemeval-cleaned", split="longmemeval_oracle")

    print(f"Number of instances: {len(longmemeval)}")
    print(f"Fields: {list(longmemeval[0].keys())}")

    # Examine one instance
    instance = longmemeval[0]
    print(f"\nQuestion type: {instance['question_type']}")
    print(f"Question: {instance['question']}")
    print(f"Answer: {instance['answer']}")
    print(f"Question date: {instance['question_date']}")
    print(f"Number of sessions: {len(instance['haystack_sessions'])}")
    print(f"Evidence session IDs: {instance['answer_session_ids']}")

    # Count by question type
    type_counts = collections.Counter(inst["question_type"] for inst in longmemeval)
    print("\nQuestion type distribution:")
    for qtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {qtype}: {count}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    To evaluate your memory system on LongMemEval, you'd follow the same pattern: ingest the sessions, answer each question using your retrieval, then score with the LLM judge. The dataset's `has_answer` field on individual turns lets you also measure retrieval recall (whether your system found the right turns).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Tradeoffs

    ### When Memory Benchmarks Work Well

    - **Diagnosing weaknesses.** Per-category scores pinpoint exactly which memory capability needs work. A single overall score hides this information.
    - **Comparing approaches.** You can objectively compare two memory architectures (vector retrieval vs. graph memory, for example) on the same questions.
    - **Tracking progress.** Run the benchmark after each change to your memory system. Scores going up means your changes helped. Scores going down means you introduced a regression (a change that makes things worse).
    - **Standardized communication.** "Our system scores 78% on LoCoMo multi-hop" is clearer than "our system has good cross-session reasoning."

    ### When They Break Down

    - **Distribution mismatch.** LoCoMo conversations are between friends chatting about life. If your system handles technical support tickets, the benchmark may not reflect real performance. Benchmark scores transfer best when the conversation style matches your use case.
    - **Cost of full evaluation.** Running all 2,000 LoCoMo questions through your memory system and an LLM judge costs real API money. Budget about $5-15 per full run with GPT-4o-mini.
    - **Metric limitations.** Text overlap metrics (BLEU, ROUGE, F1) penalize correct answers that use different wording. The LLM judge helps, but it's not perfect either. Always spot-check a sample of "incorrect" predictions.
    - **Static snapshots.** These benchmarks test a fixed set of conversations and questions. They can't capture every edge case your system will encounter in production. Use them as a floor, not a ceiling.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Further Reading

    - [Maharana et al., "Evaluating Very Long-Term Conversational Memory of LLM Agents," 2024 (arXiv:2402.17753)](https://arxiv.org/abs/2402.17753) - The LoCoMo paper. Defines the benchmark, question taxonomy, and baseline evaluations across multiple memory architectures.
    - [LoCoMo GitHub Repository](https://github.com/snap-research/LoCoMo) - Benchmark data, evaluation scripts, and baseline implementations.
    - [Wu et al., "LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory," 2024 (arXiv:2410.10813)](https://arxiv.org/abs/2410.10813) - The LongMemEval paper. Covers five core memory abilities and evaluation across commercial chat assistants.
    - [LongMemEval GitHub Repository](https://github.com/xiaowu0162/LongMemEval) - Benchmark data, evaluation code, and results.
    - [HuggingFace Evaluate Library](https://huggingface.co/docs/evaluate?utm_source=nirdiamant&utm_medium=github&utm_campaign=agent_memory_techniques) - Standardized metric implementations for BLEU, ROUGE, F1, and more.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    *\u2190 Previous: [28 - Memory Evaluation](../28_memory_evaluation/) \u00b7 Next: [30 - Production Memory Patterns](../30_production_memory_patterns/) \u2192*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 🧪 Try It Yourself

    Three small challenges to deepen your understanding. Each should take 10-30 minutes.

    ### Challenge 1: Per-category breakdown
    Run `score_all_predictions()` and group results by the 5 LoCoMo question categories: single-hop, multi-hop, temporal, open-ended, and adversarial. Print a table with F1 and ROUGE-L per category. Identify the category where your system performs worst.

    ### Challenge 2: Context window ablation
    Vary the number of retrieved context passages fed to `generate_prediction()`: try 1, 3, 5, and 10 passages. For each setting, compute the average token F1 and `llm_judge_score()`. Plot passages vs. score to find the point of diminishing returns.

    ### Challenge 3: Two-system benchmark
    Run the same LoCoMo eval suite on two different memory systems (e.g., keyword-overlap retrieval vs. embedding-based retrieval). Use `score_all_predictions()` for both and compare per-category results side by side. This builds directly on the evaluation harness from 28 Memory Evaluation.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![](https://europe-west1-amt-views-tracker.cloudfunctions.net/amt-tracker?notebook=all-techniques--29-memory-benchmarks-locomo--memory-benchmarks-locomo)
    """)
    return



@app.cell(hide_code=True)
def _():
    import marimo as _studio_mo
    studio_notes = _studio_mo.ui.text_area(label="Research notes", placeholder="Record parameters, observations and follow-up questions")
    _studio_mo.vstack([_studio_mo.md("### Research notebook"), studio_notes])
    return (studio_notes,)

if __name__ == "__main__":
    app.run()
