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
    # End-to-End RAG Evaluation

    ## Overview

    This tutorial walks through building a complete evaluation pipeline for Retrieval-Augmented Generation (RAG) systems. Rather than relying on a single metric, we combine multiple evaluation dimensions - completeness, factual accuracy, and hallucination detection - into a unified pipeline.

    ### What you'll learn:
    - How to choose evaluation criteria based on real failure patterns
    - Building custom LLM-as-a-judge metrics for completeness
    - Using RAGAS for hallucination detection
    - Assembling a full end-to-end evaluation pipeline

    ### Prerequisites:
    - OpenAI API key
    - Basic understanding of RAG systems
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Utils
    """)
    return


@app.cell
def _():
    import asyncio
    import os
    from typing import Union, List, Optional, Type
    from openai import AsyncOpenAI
    import random
    from pydantic import BaseModel, Field
    import dotenv
    import pandas as pd

    dotenv.load_dotenv()

    # Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    MODEL_NAME = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)


    async def run_llm_call(system_prompt: str, user_prompt: str,
                           response_model: Optional[Type[BaseModel]] = None,
                           model: str = MODEL_NAME) -> Union[str, None]:
        max_retries = 5
        base_delay = 30

        for attempt in range(1, max_retries + 1):
            try:
                if response_model:
                    response = await client.beta.chat.completions.parse(
                        model=model,
                        messages=[
                            {'role': 'system', 'content': system_prompt.strip()},
                            {'role': 'user', 'content': user_prompt.strip()},
                        ],
                        temperature=0,
                        response_format=response_model
                    )
                    return response.choices[0].message.parsed
                else:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {'role': 'system', 'content': system_prompt.strip()},
                            {'role': 'user', 'content': user_prompt.strip()},
                        ],
                        temperature=0,
                    )
                    return response.choices[0].message.content.strip()
            except Exception as e:
                print(f'Attempt {attempt} - OpenAI Error: {e}')
                if attempt == max_retries:
                    return None
                sleep_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(sleep_time)


    async def run_llm_calls(system_prompts: List[str], user_prompts: List[str],
                            response_model: Optional[Type[BaseModel]] = None,
                            model: str = MODEL_NAME) -> List[str]:
        tasks = [
            run_llm_call(system_prompt, user_prompt, model=model,
                         response_model=response_model)
            for system_prompt, user_prompt in zip(system_prompts, user_prompts)
        ]
        return await asyncio.gather(*tasks)

    return BaseModel, os, pd, run_llm_calls


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Step 1 - Choosing Evaluation Criteria

    Define what “good” means for your use case. We'll identify key dimensions like relevance, accuracy, fluency, and helpfulness, based on your product goals provided via feedback of human annotators.
    """)
    return


@app.cell
def _(pd):
    df = pd.read_csv('https://figshare.com/ndownloader/files/53919875')
    df.head(2)
    return (df,)


@app.cell
def _(df):
    # We will start by manually reviewing some of the manual annotation reasons
    # To get a sense of the use case and its potential issues

    df[df['annotation'] == 'bad']['annotation_reasoning'].sample(5).values.tolist()
    return


@app.cell
async def _(df, run_llm_calls):
    # We will use an llm to analyze the feedback and summarize the common problems
    # in the agent responses.
    sys_message_analyze_reasons = '\nYou are an amazing data analyst analyzing user feedback provided for a question answering agent responses.\nYour task is to analyze the user feedback and summarize the what are the common problemsin the agent responses.\nreturn up to 5 common problems.\n'.strip()
    only_bad = df[df['annotation'] == 'bad'].copy()
    _responses = await run_llm_calls(system_prompts=[sys_message_analyze_reasons], user_prompts=['\n'.join(only_bad['annotation_reasoning'].tolist())])
    print(_responses[0])
    return (only_bad,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Based on the analysis above, the errors can be grouped into four categories:

    1. Incomplete - Missing key information or context

    2. Inconscise - Unnecessarily wordy or repetitive responses

    3. Hallucinations - Fabricated or factually incorrect content

    4. Contradictions - Statements that conflict with the source or other parts of the response

    ### Divide and Conquer
    Although it's technically possible to evaluate all four criteria in a single LLM-as-a-judge call, recent studies-and the collective experience of many practitioners-show that RAG evaluation is complex. Breaking the task into smaller, focused components usally delivers better accuracy and insight.

    We’ll start by implementing an LLM-as-a-judge method to evaluate *completeness*.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Step 2 - Building the Benchmark for Completeness
    Why does this deserve its own section? Because the naive approach is tempting-but wrong.

    Not every sample labeled as “bad” is bad due to low completeness. If we don’t filter carefully, we risk evaluating against the wrong signals. To build a meaningful benchmark, we need to isolate true negatives-cases that are specifically incomplete, not flawed for other reasons like hallucinations or contradictions.

    And since we’re not fans of manual work, we’ll use our BFF ChatGPT to help automate the filtering.
    """)
    return


@app.cell
async def _(BaseModel, df, only_bad, run_llm_calls):
    system_prompt_is_complete = '\nYou are evaluating whether a response from a question-answering agent is incomplete.\n\nYour task: Based on the user feedback, determine if the primary issue with the agent’s answer is a **completeness problem**-i.e., it is missing key information that should have been included. If the issue is due to something else (e.g., hallucination, contradiction, poor phrasing), mark it as not related to completeness.\n\nRespond with a clear yes/no judgment and a brief reasoning.\n'.strip()
    user_prompt_reasoning_eval = '\nQuestion:\n{question}\n\nWrong Answer:\n{output}\n\nAnnotation Reasoning:\n{reasoning}\n'.strip()

    class CompletenessRelated(BaseModel):
        reasoning: str
        has_completeness_problem: bool
    _sys_msgs = [system_prompt_is_complete] * df.shape[0]
    user_msgs = [user_prompt_reasoning_eval.format(question=row['input'], output=row['output'], reasoning=row['annotation_reasoning']) for _, row in only_bad.iterrows()]
    _responses = await run_llm_calls(_sys_msgs, user_msgs, response_model=CompletenessRelated)
    only_bad['completeness_related'] = [r.has_completeness_problem for r in _responses]
    only_bad['completeness_related'].value_counts()
    return (user_prompt_reasoning_eval,)


@app.cell
def _(df, only_bad, pd):
    # For the sake of getting a sample which is representative of the data but not overly unbalanced
    # we will use 20 examples of the positive class and the 10 examples of the negative class.

    only_good = df[df['annotation'] == 'good'].copy()
    completeness_eval_df = pd.concat([only_good.sample(20, random_state=1), only_bad[only_bad['completeness_related']]])
    completeness_eval_df['annotation'] = completeness_eval_df['annotation'].replace({'good': 1, 'bad': 0})

    print(completeness_eval_df.shape)
    completeness_eval_df.head(2)
    return completeness_eval_df, only_good


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Step 3 - Completeness Metric

    We'll use an LLM to assess whether each output is complete. First, we'll implement a simple baseline approach-then iterate to improve accuracy and reliability.
    """)
    return


@app.cell
async def _(BaseModel, completeness_eval_df, run_llm_calls):
    from enum import Enum
    from sklearn.metrics import classification_report
    _system_prompt_completeness_eval = '\nDecide if the answer is missing important information based on the question.\n\nIs the answer complete? Answer complete or incomplete.\n'.strip()
    user_prompt_answer_eval = '\nQuestion:\n{question}\n\nContext:\n{context}\n\nAnswer:\n{conclusions}\n'.strip()

    class _ScoreValue(int, Enum):
        INCOMPLETE = 0
        COMPLETE = 1

    class _CompletenessScore(BaseModel):
        score: _ScoreValue
    _sys_msgs = [_system_prompt_completeness_eval] * completeness_eval_df.shape[0]
    user_msgs_1 = [user_prompt_answer_eval.format(question=row['input'], context=row['information_retrieved'], conclusions=row['output']) for _, row in completeness_eval_df.iterrows()]
    _responses = await run_llm_calls(_sys_msgs, user_msgs_1, response_model=_CompletenessScore)
    completeness_eval_df['naive_method'] = [int(x.score.value) for x in _responses]
    print(completeness_eval_df.naive_method.value_counts())
    classification_report(completeness_eval_df.annotation, completeness_eval_df.naive_method, output_dict=True, zero_division=0)
    return Enum, classification_report, user_msgs_1


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The naive method struggles to identify *incomplete negative examples* accurately. This shows the problem is more complex than it seems-and not easily solved with a simple approach. Let’s explore more advanced methods to handle it more effectively.
    """)
    return


@app.cell
async def _(
    BaseModel,
    Enum,
    classification_report,
    completeness_eval_df,
    run_llm_calls,
    user_msgs_1,
):
    _system_prompt_completeness_eval = '\nYou are an assistant evaluating how complete an answer is, given a question and supporting context.\n\nFirst, consider what are the key pieces of information a fully complete answer should include based on the question and context.  \nThen, check whether the answer contains all of that information.\n\nProvide a short explanation of your reasoning.  \nThen assign a score:\n\n0 - Not complete: Key information is missing or major parts of the question are not addressed.  \n1 - Partially complete: All parts of the question are touched on, but some are incomplete or only loosely supported by the context.  \n2 - Fully complete: The answer thoroughly and directly addresses all aspects of the question, using information clearly supported by the context.\n'.strip()

    class _ScoreValue(int, Enum):
        INCOMPLETE = 0
        PARTIALLY_COMPLETE = 1
        COMPLETE = 2

    class _CompletenessScore(BaseModel):
        reasoning: str
        score: _ScoreValue
    _sys_msgs = [_system_prompt_completeness_eval] * completeness_eval_df.shape[0]
    _responses = await run_llm_calls(_sys_msgs, user_msgs_1, response_model=_CompletenessScore, model='gpt-4.1-mini')
    completeness_eval_df['advenced_method'] = [int(x.score > 1) for x in _responses]
    completeness_eval_df['advenced_method_reasoning'] = [x.reasoning for x in _responses]
    print(completeness_eval_df.advenced_method.value_counts())
    classification_report(completeness_eval_df.annotation, completeness_eval_df.advenced_method, output_dict=True, zero_division=0)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The advanced method performs well and reliably identifies incomplete answers. While there’s still some room for fine-tuning, it’s accurate enough for practical use.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Step 4 - Utilize RAGAS for hallucination detection
    """)
    return


@app.cell
async def _(
    BaseModel,
    df,
    only_bad,
    run_llm_calls,
    user_prompt_reasoning_eval,
):
    system_prompt_is_factually_correct = '\nYou are evaluating whether a response from a question-answering agent has a **factual correctness problem**.\n\nYour task: Based on the user feedback, determine if the main issue with the answer is related to **hallucination** (made-up or incorrect information) or **contradiction** (statements that conflict with known facts or the context). If the issue is something else (e.g., incomplete, vague, poorly phrased), mark it as not related to factual correctness.\n\nRespond with a clear yes/no judgment and a brief explanation.\n'.strip()

    class FactualRelated(BaseModel):
        reasoning: str
        has_factual_correctness_problem: bool
    _sys_msgs = [system_prompt_is_factually_correct] * df.shape[0]
    user_msgs_2 = [user_prompt_reasoning_eval.format(question=row['input'], output=row['output'], reasoning=row['annotation_reasoning']) for _, row in only_bad.iterrows()]
    _responses = await run_llm_calls(_sys_msgs, user_msgs_2, response_model=FactualRelated)
    only_bad['factual_related'] = [r.has_factual_correctness_problem for r in _responses]
    print(only_bad['factual_related'].value_counts())
    return


@app.cell
def _(only_bad, only_good, pd):
    factual_eval_df = pd.concat([only_good.sample(sum(only_bad['factual_related']), random_state=1),
                                 only_bad[only_bad['factual_related']]])
    factual_eval_df['annotation'] = factual_eval_df['annotation'].replace({'good': 1, 'bad': 0})
    return (factual_eval_df,)


@app.cell
def _(classification_report, factual_eval_df, os):
    # Test RAGAS
    from ragas.metrics import faithfulness
    from ragas.dataset_schema import SingleTurnSample
    from langchain.chat_models import ChatOpenAI
    from ragas import evaluate, EvaluationDataset
    langchain_client = ChatOpenAI(model_name='gpt-4.1', openai_api_key=os.environ['OPENAI_API_KEY'], temperature=0)
    samples = [SingleTurnSample(user_input=row['input'], response=row['output'], retrieved_contexts=[row['information_retrieved']]) for _, row in factual_eval_df.iterrows()]
    results = evaluate(EvaluationDataset(samples=samples), metrics=[faithfulness], llm=langchain_client)
    factual_eval_df['ragas_faithfulness'] = [r['faithfulness'] for r in results.scores]
    factual_eval_df['ragas_faithfulness_binary'] = [1 if r['faithfulness'] > 0.5 else 0 for r in results.scores]
    print(factual_eval_df.ragas_faithfulness_binary.value_counts())
    classification_report(factual_eval_df.annotation, factual_eval_df.ragas_faithfulness_binary, output_dict=True)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Unfortunately, even the most advanced open-source tools often fall short on complex tasks. While they perform well in general settings, they don’t meet the specific needs of our use case. Addressing this gap will require targeted research to develop a factual correctness tool tailored to our domain. One example of a non-LLM-based approach can be found [here](https://arxiv.org/abs/2504.15771).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Step 5 - Aggragate to an end-2-end evaluation pipeline

    At this stage, we combine all evaluation steps into a full end-to-end pipeline. Each sample-input, context, and LLM output-is judged on whether the output is good enough, from a domain expert’s perspective, to be sent to a client. With a representative test set, this pipeline helps measure the real-world performance of the application and track what actual application quality.

    When aggregating evaluation results, simply averaging scores across criteria can be misleading-some dimensions may mask critical weaknesses in others. Instead of collapsing everything into a single number, it’s often better to treat each criterion independently. The approach we will take here is to define pass/fail thresholds per criterion and only consider an output successful if it meets all of them. Another option is to use logical rules (e.g., must pass factual accuracy and clarity, but fluency can be slightly relaxed) or weighted thresholds tailored to the use case. The key is to reflect real-world standards-especially when outputs are client-facing and failure in one area can undermine the whole result.
    """)
    return


@app.cell
def _(
    COMPLETENESS_THRESHOLD,
    FACTUALITY_THRESHOLD,
    classification_report,
    df,
    evalaute_completeness_via_llm_as_judge,
    evalaute_factuality_via_ragas,
):
    # Is this example we will only take into account evaluation of completeness and factual correctness
    # We will use the advanced method for completeness and the RAGAS for factual correctness

    def get_final_annotation(row):
        factual_score = evalaute_factuality_via_ragas(row)
        completeness_score = evalaute_completeness_via_llm_as_judge(row)

        if factual_score < FACTUALITY_THRESHOLD:
            return "bad", "factuality problem"
        elif completeness_score < COMPLETENESS_THRESHOLD:
            return "bad", "completeness problem"
        return "good", ""


    df['automated_annotation_pipeline'] = df.apply(get_final_annotation, axis=1)
    classification_report(
        df.annotation,
        df.automated_annotation_pipeline,
        output_dict=True,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Summary

    This notebook demonstrated a complete RAG evaluation pipeline that combines:

    1. **Custom criteria selection** based on real failure analysis
    2. **LLM-as-a-judge completeness metric** with naive vs. advanced approaches
    3. **RAGAS-based hallucination detection** for factual accuracy
    4. **End-to-end pipeline assembly** combining all metrics into a unified score

    The key insight: evaluation is iterative. Start with simple metrics, analyze where they fail, then build more sophisticated ones. No single metric captures everything - combine multiple dimensions for a reliable signal.
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
