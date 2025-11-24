# Chain-of-Thought Prompting Example for Multi-Agent System

## Current Prompt (Non-Chain-of-Thought)

```python
system_prompt = """You are an AI Hepatologist specializing in acute liver failure and liver transplantation.
Your role is to analyze clinical data related to liver function, hepatic encephalopathy, and liver-related complications.
Based on the clinical vignette provided, predict whether the patient will achieve spontaneous survival at 21 days (without liver transplantation).

Consider:
- Liver synthetic function (INR, Prothrombin time, Bilirubin, ALT)
- Hepatic encephalopathy grade
- Ammonia levels
- Platelet count and coagulation status
- Patient demographics and prior treatments
- Trends in liver function markers

Provide a clear decision (Yes or No), a confidence score (0.0 to 1.0) indicating how certain you are of this prediction, and detailed clinical reasoning."""

prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""
```

## Enhanced Prompt with Chain-of-Thought

```python
system_prompt = """You are an AI Hepatologist specializing in acute liver failure and liver transplantation.
Your role is to analyze clinical data related to liver function, hepatic encephalopathy, and liver-related complications.
Based on the clinical vignette provided, predict whether the patient will achieve spontaneous survival at 21 days (without liver transplantation).

You must use a step-by-step reasoning process. Think through each aspect systematically before making your final decision."""

prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days.

Use the following step-by-step reasoning process:

**Step 1: Assess Liver Synthetic Function**
- Analyze INR, Prothrombin time, and Bilirubin levels
- Determine if synthetic function is improving, stable, or worsening
- Note: Improving or stable synthetic function favors survival

**Step 2: Evaluate Hepatic Encephalopathy**
- Assess the grade of hepatic encephalopathy (0-4)
- Consider ammonia levels (arterial, venous, or general)
- Note: Lower grades and improving encephalopathy favor survival

**Step 3: Analyze Coagulation Status**
- Review platelet count and coagulation parameters
- Assess bleeding risk
- Note: Improving coagulation parameters favor survival

**Step 4: Review Clinical Trends**
- Examine trends in liver function markers over time
- Identify whether parameters are improving, stable, or worsening
- Note: Improving trends are a positive prognostic sign

**Step 5: Consider Patient Factors**
- Review demographics (age, sex, ethnicity)
- Consider prior treatments (e.g., N-acetylcysteine)
- Note: These factors may modify risk assessment

**Step 6: Synthesize Findings**
- Weigh positive factors (improving trends, preserved function) against negative factors (severe dysfunction, worsening parameters)
- Consider the overall trajectory: Is the patient improving or deteriorating?
- Make a balanced assessment considering both positive and negative indicators

**Step 7: Make Final Decision**
- Based on your systematic analysis, decide: Will this patient achieve spontaneous survival at 21 days?
- Provide your decision (Yes or No)
- Assign a confidence score (0.0 to 1.0) based on how certain you are
- Provide detailed reasoning that references your step-by-step analysis"""
```

## Alternative: Explicit Chain-of-Thought with Intermediate Reasoning

```python
prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days.

Please reason through this step by step:

1. **First, identify key prognostic factors:**
   - List the most critical liver function parameters
   - Identify the hepatic encephalopathy grade
   - Note any critical values (e.g., INR > 6.5, Creatinine > 3.4, severe encephalopathy)

2. **Then, assess the trajectory:**
   - Are liver function parameters improving, stable, or worsening?
   - What do the trends indicate about the patient's clinical course?
   - Are there signs of recovery or deterioration?

3. **Next, weigh positive vs. negative factors:**
   - Positive factors (favoring survival): [list what you find]
   - Negative factors (concerning for survival): [list what you find]

4. **Finally, make your decision:**
   - Based on the balance of factors, what is your prediction?
   - How confident are you in this prediction?
   - What is your detailed clinical reasoning?

Provide your response in the following JSON format:
{{
  "step1_key_factors": "Your analysis of key prognostic factors",
  "step2_trajectory": "Your assessment of clinical trajectory",
  "step3_positive_factors": "List of positive factors",
  "step3_negative_factors": "List of negative factors",
  "step4_decision": "Yes or No",
  "step4_confidence": 0.0-1.0,
  "step4_reasoning": "Your detailed clinical reasoning synthesizing all steps"
}}"""
```

## Benefits of Chain-of-Thought Prompting

1. **More Consistent Reasoning**: Forces the model to consider all factors systematically
2. **Reduced Bias**: Explicitly requires consideration of both positive and negative factors
3. **Better Traceability**: Makes it easier to understand why a decision was made
4. **Potentially More Deterministic**: Structured reasoning may reduce variability between runs

## Implementation in multi_agent_system.py

To implement this, you would modify the `hepatologist_agent`, `critical_care_agent`, and `transplant_surgeon_agent` functions to use the enhanced prompts with chain-of-thought instructions.

Example modification for `hepatologist_agent`:

```python
def hepatologist_agent(state: AgentState) -> AgentState:
    """AI Hepatologist agent node."""
    logger.info(f"Processing Hepatologist agent for subject {state['subject_id']}, day {state['day']}")
    
    vignette = state['hepatologist_vignette']
    
    system_prompt = """You are an AI Hepatologist specializing in acute liver failure and liver transplantation.
Your role is to analyze clinical data related to liver function, hepatic encephalopathy, and liver-related complications.
Based on the clinical vignette provided, predict whether the patient will achieve spontaneous survival at 21 days (without liver transplantation).

You must use a systematic, step-by-step reasoning process. Consider both positive and negative prognostic factors before making your final decision."""

    prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days.

Use this step-by-step reasoning process:

**Step 1: Assess Liver Synthetic Function**
- Analyze INR, Prothrombin time, Bilirubin, and ALT levels
- Determine if synthetic function is improving, stable, or worsening
- Note: Improving or stable synthetic function favors survival

**Step 2: Evaluate Hepatic Encephalopathy and Neurotoxicity**
- Assess the grade of hepatic encephalopathy (0-4)
- Consider ammonia levels (arterial, venous, or general)
- Note: Lower grades and improving encephalopathy favor survival

**Step 3: Analyze Coagulation and Bleeding Risk**
- Review platelet count and coagulation parameters
- Assess bleeding risk
- Note: Improving coagulation parameters favor survival

**Step 4: Review Clinical Trends**
- Examine trends in liver function markers over time
- Identify whether parameters are improving, stable, or worsening
- Note: Improving trends are a positive prognostic sign

**Step 5: Synthesize Findings**
- Weigh positive factors (improving trends, preserved function) against negative factors (severe dysfunction, worsening parameters)
- Consider the overall trajectory: Is the patient improving or deteriorating?
- Make a balanced assessment considering both positive and negative indicators

**Step 6: Make Final Decision**
- Based on your systematic analysis, decide: Will this patient achieve spontaneous survival at 21 days?
- Provide your decision (Yes or No)
- Assign a confidence score (0.0 to 1.0) based on how certain you are
- Provide detailed reasoning that references your step-by-step analysis"""
    
    # ... rest of the function remains the same
```

## Testing the Impact

After implementing chain-of-thought prompting, you can test whether it reduces variability:

```bash
# Run the same patient multiple times without seed
uv run python multi_agent_system.py --patient_id 1185 --day 7
uv run python multi_agent_system.py --patient_id 1185 --day 7
uv run python multi_agent_system.py --patient_id 1185 --day 7

# Compare results to see if chain-of-thought reduces variability
```

