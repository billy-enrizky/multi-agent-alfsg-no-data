import os
import json
import logging
import argparse
import pandas as pd
import time
import re
from typing import Literal, TypedDict, Optional, Union
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from openai import OpenAI
from anthropic import AnthropicFoundry, transform_schema
from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def clean_json_string(json_str: str) -> str:
    """Remove invalid control characters from JSON string that can cause parsing errors."""
    # Remove control characters except \t, \n, \r (valid whitespace in JSON)
    cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', json_str)
    return cleaned

# Pydantic models for structured outputs
class AgentDecision(BaseModel):
    """Individual agent decision output."""
    decision: Literal["Yes", "No"] = Field(description="Prediction: Will patient survive 21 days? Yes or No")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="Detailed clinical reasoning for the decision")

class FinalPrediction(BaseModel):
    """Final committee prediction output."""
    prediction: Literal["Yes", "No"] = Field(description="Final prediction: Will patient survive 21 days? Yes or No")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="Synthesis of all agent inputs with weighted analysis")

# State definition for LangGraph
class AgentState(TypedDict):
    """State passed between nodes in the graph."""
    subject_id: int
    day: int
    vignette: str
    hepatologist_output: AgentDecision | None
    critical_care_output: AgentDecision | None
    transplant_surgeon_output: AgentDecision | None
    final_prediction: FinalPrediction | None

def get_azure_openai_client(deployment_name: str = None):
    """Initialize client (OpenAI or Anthropic Foundry) based on deployment name.
    
    Args:
        deployment_name: The deployment/model name. If None, uses DEPLOYMENT_NAME env var or defaults to 'gpt-5'.
    """
    if deployment_name is None:
        deployment_name = os.getenv("DEPLOYMENT_NAME", "gpt-5")
    
    # Convert deployment name to environment variable prefix
    # e.g., "gpt-5" -> "GPT5", "gpt-4.1-mini" -> "GPT4_1_MINI", "gpt-5-mini" -> "GPT5_MINI"
    # Anthropic models: "claude-opus-4-1" -> "OPUS4_1", "claude-sonnet-4-5" -> "SONNET4_5"
    if deployment_name == "claude-opus-4-1":
        deployment = "OPUS4_1"
    elif deployment_name == "claude-sonnet-4-5":
        deployment = "SONNET4_5"
    else:
        deployment = deployment_name.replace("-", "_").replace(".", "_").upper()
        # Special handling: remove underscore between GPT and number (e.g., "GPT_5" -> "GPT5")
        deployment = deployment.replace("GPT_", "GPT")
    
    endpoint = os.getenv(f"{deployment}_ENDPOINT_URL")
    
    # Check if using Anthropic Foundry (claude models)
    if deployment_name in ["claude-opus-4-1", "claude-sonnet-4-5"]:
        # Use deployment-specific API key
        api_key = os.getenv(f"{deployment}_ANTHROPIC_API_KEY")
        if not api_key:
            # Fallback to generic API key
            api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(f"{deployment}_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY environment variable is required for Anthropic Foundry")
        client = AnthropicFoundry(
            api_key=api_key,
            base_url=endpoint
        )
        return client, deployment_name, "anthropic"
    else:
        # Default to OpenAI - use deployment-specific API key
        api_key = os.getenv(f"{deployment}_AZURE_OPENAI_API_KEY")
        if not api_key:
            # Fallback to generic API key
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if not api_key:
            raise ValueError(f"{deployment}_AZURE_OPENAI_API_KEY or AZURE_OPENAI_API_KEY environment variable is required")
        client = OpenAI(
            base_url=f"{endpoint}",
            api_key=api_key
        )
        return client, deployment_name, "openai"


def call_llm(client, client_type: str, deployment_name: str, system_prompt: str, user_prompt: str, json_mode: bool = False, json_schema_model=None):
    """Unified function to call either OpenAI or Anthropic API.
    
    Args:
        client: The client instance (OpenAI or AnthropicFoundry)
        client_type: "openai" or "anthropic"
        deployment_name: Model/deployment name
        system_prompt: System prompt
        user_prompt: User prompt
        json_mode: Whether to request JSON output
        json_schema_model: Pydantic model for JSON schema (AgentDecision or FinalPrediction)
    
    Returns:
        For Anthropic with json_mode=True and json_schema_model: Returns the parsed Pydantic model directly
        Otherwise: Returns response text as string
    """
    if client_type == "anthropic":
        # Check if using claude-opus-4-1 and enable extended thinking
        use_thinking = (deployment_name == "claude-opus-4-1")
        
        # Anthropic API - Use native structured outputs when available
        if json_mode and json_schema_model:
            try:
                # Use beta.messages.parse() for native structured outputs (returns parsed Pydantic model directly)
                parse_kwargs = {
                    "model": deployment_name,
                    "max_tokens": 16384,  # Must be > thinking.budget_tokens (10000)
                    "betas": ["structured-outputs-2025-11-13"],
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_prompt}
                    ],
                    "output_format": json_schema_model,
                }
                
                # Add thinking parameter for claude-opus-4-1
                if use_thinking:
                    parse_kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": 10000
                    }
                    parse_kwargs["temperature"] = 1  # Must be 1 when thinking is enabled
                else:
                    parse_kwargs["temperature"] = 0  # Use 0 for deterministic outputs when thinking is disabled
                
                response = client.beta.messages.parse(**parse_kwargs)
                # Return the parsed Pydantic model directly
                return response.parsed_output
            except Exception as e:
                logger.warning(f"Anthropic structured outputs failed, falling back to manual parsing: {e}")
                # Fallback to manual JSON parsing
                json_schema = json_schema_model.model_json_schema()
                
                # Determine the correct field name based on the model
                # AgentDecision uses "decision", FinalPrediction uses "prediction"
                if json_schema_model == FinalPrediction:
                    decision_field = "prediction"
                else:
                    decision_field = "decision"
                
                user_prompt = f"""{user_prompt}

You must respond with a JSON object containing these exact fields:
- "{decision_field}": either "Yes" or "No" (string)
- "confidence": a number between 0.0 and 1.0 (float)
- "reasoning": a detailed explanation (string)

Example JSON format:
{{
  "{decision_field}": "Yes",
  "confidence": 0.85,
  "reasoning": "Your detailed reasoning here"
}}

Full JSON schema for reference:
{json.dumps(json_schema, indent=2)}

Return only valid JSON, no additional text."""
        
        # Regular message creation (for non-JSON mode or fallback)
        create_kwargs = {
            "model": deployment_name,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 16384,  # Must be > thinking.budget_tokens (10000)
        }
        
        # Add thinking parameter for claude-opus-4-1
        if use_thinking:
            create_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": 10000
            }
            create_kwargs["temperature"] = 1  # Must be 1 when thinking is enabled
        else:
            create_kwargs["temperature"] = 0  # Use 0 for deterministic outputs when thinking is disabled
        
        message = client.messages.create(**create_kwargs)
        
        # Extract text from Anthropic response (list of content blocks)
        if not message.content:
            logger.error("Anthropic response has no content")
            return ""
        
        # Handle different content block types (including thinking blocks)
        response_text = ""
        for block in message.content:
            # Handle thinking blocks (extended thinking feature)
            if hasattr(block, 'type'):
                if block.type == "thinking":
                    # Thinking blocks contain summarized thinking - we can log but don't include in response
                    if hasattr(block, 'thinking'):
                        logger.debug(f"Thinking summary: {block.thinking}")
                    continue
                elif block.type == "text":
                    if hasattr(block, 'text'):
                        response_text += block.text
                    continue
            # Fallback for other block types
            if hasattr(block, 'text'):
                response_text += block.text
            elif isinstance(block, dict) and 'text' in block:
                response_text += block['text']
            elif isinstance(block, str):
                response_text += block
        
        if not response_text:
            logger.error(f"Anthropic response content is empty. Content structure: {message.content}")
            return ""
        
        # Extract JSON from markdown code blocks if present (Anthropic often wraps JSON in ```json ... ```)
        response_text = response_text.strip()
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end > start:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            # Handle generic code blocks
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end > start:
                response_text = response_text[start:end].strip()
        
        return response_text
    else:
        # OpenAI API
        if json_mode:
            # OpenAI requires the word "json" in messages when using response_format={"type": "json_object"}
            if json_schema_model:
                # Get the properties we need, not the full schema
                json_schema = json_schema_model.model_json_schema()
                # Extract just the properties we need
                properties = json_schema.get('properties', {})
                
                # Determine the correct field name based on the model
                # AgentDecision uses "decision", FinalPrediction uses "prediction"
                if json_schema_model == FinalPrediction:
                    decision_field = "prediction"
                else:
                    decision_field = "decision"
                
                user_prompt_with_json = f"""{user_prompt}

You must respond with a JSON object containing these exact fields:
- "{decision_field}": either "Yes" or "No" (string)
- "confidence": a number between 0.0 and 1.0 (float)
- "reasoning": a detailed explanation (string)

Example JSON format:
{{
  "{decision_field}": "Yes",
  "confidence": 0.85,
  "reasoning": "Your detailed reasoning here"
}}

Return only the JSON object, no additional text or explanation."""
            else:
                # Ensure "json" is in the prompt
                user_prompt_with_json = f"""{user_prompt}

Please respond with a valid JSON object. Return only JSON, no additional text."""
            
            completion = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt_with_json}
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=16384,
                seed=42,  # Use seed for deterministic outputs (GPT-5 doesn't support temperature=0)
            )
        else:
            completion = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_completion_tokens=16384,
            )
        
        response_text = completion.choices[0].message.content
        return response_text

def hepatologist_agent(state: AgentState) -> AgentState:
    """AI Hepatologist agent node."""
    logger.info(f"Processing Hepatologist agent for subject {state['subject_id']}, day {state['day']}")
    
    vignette = state['vignette']
    
    system_prompt = """# Role
You are an AI Hepatologist specializing in Acute Liver Failure (ALF). Your primary responsibility is to analyze biochemical trends to determine if the liver is regenerating or if irreversible necrosis has occurred, across all ALF etiologies.

# Objective
Predict whether the patient will achieve **Spontaneous Survival (without transplant)** at 21 days.

# Evidence Base
Your reasoning should be grounded in the following peer-reviewed evidence:
- Koch 2016: ALFSG Prognostic Index (ALFSG-PI) model for predicting 21-day transplant-free survival (TFS). C statistic 0.84, outperforms King's College Criteria (APAP C=0.560, non-APAP C=0.655) and MELD (C=0.717).
- Dong 2024: Outcomes of non-listed ALF patients. ALFSG-PI independently associated with survival (aOR 0.06 for mortality per unit increase).
- Karvellas 2023: Outcomes of listed ALF patients. 20% of listed patients spontaneously recovered without transplant.

# Knowledge Base & Skills
1. **ALFSG Prognostic Index (Koch 2016):** The validated ALFSG-PI score is provided in the clinical vignette. The model uses five variables: HE grade (mild vs deep), etiology severity (favorable vs unfavorable), vasopressor use, ln(bilirubin), and ln(INR). Key interpretation:
   - ALFSG-PI >= 80%: Favorable prognosis, observed TFS ~85-95%
   - ALFSG-PI 50-80%: Intermediate prognosis, observed TFS ~56-75%
   - ALFSG-PI < 50%: Poor prognosis, observed TFS ~25%
   **CRITICAL LIMITATION:** The ALFSG-PI uses ONLY 5 variables. It does NOT capture mechanical ventilation, infection/sepsis, respiratory failure (PaO2/FiO2), CRRT, lactate, or CREATININE. When a patient has severe extrahepatic organ failure, the ALFSG-PI may significantly OVERESTIMATE survival. In particular: when grade 3+ HE + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) are ALL present, this represents a near-KCC phenotype (meeting 2 of 3 APAP KCC triad criteria) PLUS ventilation -- a high-severity combination that the ALFSG-PI fundamentally underestimates because it excludes both creatinine and ventilation. Patients can die from multi-organ failure even if their liver-specific markers (INR, bilirubin) appear manageable.
2. **Etiology Severity Classification (Koch 2016):** Favorable etiologies (APAP, pregnancy, ischemia, hepatitis A) have ~68% TFS. Unfavorable etiologies (all others including indeterminate, DILI, hepatitis B, autoimmune, Wilson) have ~27% TFS.
3. **Synthetic Function Evaluation:** INR and bilirubin are the two strongest biochemical predictors in the ALFSG-PI (log-transformed). INR dynamic changes over time are statistically significant predictors. PT/INR normalization by day 4 predicts survival in ~94% of ALF cases (Poddar 2013). Prothrombin time trends provide additional context.
   **Bilirubin in Hyperacute ALF (APAP/Ischemia):** In hyperacute ALF, bilirubin is a LAGGING indicator -- it commonly continues to rise for 5-10 days after peak injury because hepatic excretory function recovers more slowly than synthetic function (coagulation factors). A rising bilirubin in the first week of APAP ALF is EXPECTED even in survivors and does NOT by itself indicate failure, particularly when INR is improving dramatically toward normal, HE is resolving, and lactate is normalizing. Do NOT let a rising bilirubin override a clear concordant recovery pattern.
   **TRUE Bilirubin-INR Dissociation (Ominous):** The bilirubin rise becomes genuinely ominous when: (a) bilirubin escalates to EXTREME levels approaching or exceeding 17 mg/dL (the non-APAP KCC threshold) -- this magnitude is atypical for APAP recovery; (b) INR improvement is only PARTIAL (remains elevated >2.0) rather than dramatic normalization; (c) other markers show DISCORDANT signals (history of prolonged deep coma, persistent organ support needs, infections). When extreme bilirubin rise coexists with discordant recovery, this is a strong mortality signal.
4. **Hepatic Encephalopathy Assessment:** HE grade is dichotomized as mild (grades 0-2) vs deep (grades 3-4) in the ALFSG-PI. Deep HE significantly reduces predicted TFS. **HE trajectory matters:** A patient who rapidly improves from grade 3 to grade 0-1 (rapid neurological clearing) has a much better prognosis than a patient who was in grade 4 coma for multiple consecutive days and only partially improved to grade 2. The ALFSG-PI captures only the current HE grade snapshot, not the trajectory or duration of deep coma. Prolonged grade 3-4 HE indicates significant neurological injury with uncertain recovery.
5. **Prognostic Criteria Application:** King's College Criteria for APAP: arterial pH < 7.3 OR triad of INR > 6.5, creatinine > 3.4 mg/dL, and grade 3/4 HE. For non-APAP: INR > 6.5 OR 3 of 5 criteria (poor etiology, jaundice-to-HE >7 days, age <10 or >40, INR >3.5, bilirubin >17 mg/dL). Note: KCC has inferior discriminative ability compared to ALFSG-PI.
6. **Extrahepatic Organ Failure Markers:** Mechanical ventilation (aOR 1.53 for mortality, Dong 2024), infection/sepsis, rising lactate, worsening PaO2/FiO2, and CRRT need are all clinically significant even though they are NOT in the ALFSG-PI model. These markers can indicate a patient will die from multi-organ failure despite favorable liver-specific markers. Assess these independently.
7. **Supplementary Biochemical Markers:** Phosphate, lactate, ammonia, and creatinine are clinically relevant but did NOT improve the ALFSG-PI model in the validation cohort. Use them for contextual assessment alongside the whole clinical picture.
8. **Treatment Response Analysis:** N-acetylcysteine efficacy depends on timing. CRRT is independently associated with reduced mortality (aOR 0.62, Dong 2024).
9. **Recovery Concordance Assessment (CRITICAL):** The strongest predictor of ALF outcome is whether improvement is CONCORDANT or DISCORDANT across organ systems:
   - **Concordant recovery** (strongly predicts survival): INR improving toward normal (<2.0) AND HE resolving toward grade 0-1 AND lactate normalizing (<2 mmol/L) AND creatinine improving AND ALT declining. When 4-5 markers improve concordantly in APAP, bilirubin may lag behind (rises for days after peak injury, typically reaching ~8-12 mg/dL) -- this does NOT negate the recovery pattern. Isolated vasopressor use with normal lactate in this context likely reflects hemodynamic support needs, NOT refractory shock.
   - **Discordant pattern** (strongly predicts death): Bilirubin escalating to extreme levels (>15 mg/dL), INR only partially improving (remains >2.0), history of prolonged deep coma (grade 3-4 HE for multiple consecutive days), continuous organ support (CVVH/CRRT for entire observation period), documented infections. Even if the current ALFSG-PI snapshot looks favorable, discordant patterns indicate failed hepatic regeneration despite supportive care.
   - **EXTREME BILIRUBIN OVERRIDE (CONTEXT-DEPENDENT):** When bilirubin rises to >15 mg/dL in APAP ALF (approaching the non-APAP KCC threshold of 17 mg/dL), this is NOT normal lagging -- it typically indicates catastrophic hepatic excretory failure. Typical APAP bilirubin lag reaches ~8-12 mg/dL. HOWEVER, this override is context-dependent: if bilirubin is 15-17 mg/dL AND full concordant recovery is present across ALL other systems (HE resolved to grade 0-1, INR < 1.5, lactate < 2.0 mmol/L, no vasopressors, no mechanical ventilation, no active infections), this may represent a variant of APAP bilirubin lag rather than catastrophic failure -- in this specific combination, do NOT automatically predict death. If bilirubin >15 mg/dL AND any other system shows discordance (HE grade 2+, INR >= 1.5, lactate >= 2.0, vasopressors, ventilation, infection), predict death.
   - **PERSISTENT GRADE 4 HE (DURATION-BASED):** APAP recovery typically shows rapid neurological clearing within 2-3 days. Persistent grade 4 HE at Day 4+ in APAP (or Day 5+ in non-APAP) is a critical death signal because 28% of ALF deaths are neurologic (cerebral edema/herniation, Karvellas 2023). The ALFSG-PI treats grades 3 and 4 identically (both "deep"), but grade 4 carries substantially higher mortality risk. Predict death when grade 4 HE persists at Day 4+ UNLESS ALL of these conditions are met: liver function FULLY normalized (INR < 1.5, bilirubin < 5 mg/dL, lactate < 2.0 mmol/L, no active infections, ALT declining) AND PaO2/FiO2 >= 2.0 (no severe ARDS -- severe ARDS with grade 4 HE suggests neurogenic pulmonary edema from cerebral edema). If grade 4 HE + PaO2/FiO2 < 2.0 are both present, predict death even if liver function is normalized -- this combination indicates likely cerebral edema with neurogenic pulmonary edema. Rising lactate strengthens this override but is NOT required -- persistent grade 4 HE alone at Day 4+ with any other concerning feature (elevated lactate, bilirubin > 5, infection, high INR, severe ARDS) is sufficient to predict death.
   - **AMMONIA CONTEXT FOR HE ASSESSMENT (Day 5+ ONLY):** Hepatic encephalopathy is driven by hyperammonemia. At Day 5+ in APAP (or Day 6+ in non-APAP), when persistent grade 3-4 HE coexists with NORMAL ammonia (<50 umol/L) AND there is an alternative explanation for the altered consciousness (elevated creatinine suggesting uremic encephalopathy, heavy sedation for mechanical ventilation, ICU delirium), the coma is likely NON-hepatic in origin. In this specific context, the deep HE does NOT carry the same cerebral edema/herniation risk and should NOT trigger the persistent HE death override. Instead, assess whether the non-hepatic causes of coma are potentially reversible. NOTE ON STALE AMMONIA: If ammonia was normal (<50 umol/L) at an earlier time point AND liver function has since recovered or normalized (INR < 1.5), ammonia is almost certainly still normal or lower because the recovered liver clears ammonia efficiently. Treat stale normal ammonia with recovered liver as CONFIRMED normal ammonia -- do NOT dismiss it as unreliable. IMPORTANT: Do NOT apply this ammonia context rule before Day 5 -- at Day 3-4, cerebral edema from earlier hyperammonemia can still be progressing even if ammonia has now normalized.
   - **CVVH AND CREATININE:** When CVVH/CRRT is active, creatinine may be artificially low because CRRT clears creatinine. Do NOT count low creatinine during active CVVH as evidence of renal recovery. The need for continuous CVVH itself is a marker of persistent organ dysfunction.
   - **EARLY PRESENTATION WITHOUT TRAJECTORY (day 1-2):** When only 1-2 days of data are available, concordant recovery CANNOT be demonstrated because there is no trajectory. Do NOT assume recovery will occur based on ALFSG-PI alone. A high-severity day-1 presentation with deep HE (grade 3+) + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) is a near-KCC phenotype that the ALFSG-PI fundamentally underestimates (it excludes creatinine and ventilation). Without demonstrated recovery, predict death when this severity pattern is present.
   - **DEMONSTRATED RECOVERY OVERRIDES INITIAL PROGNOSIS (Day 5+, NEAR-CONCLUSIVE):** When a patient at Day 5+ shows clear hepatic recovery trajectory -- INR normalized to <1.5 (from initially elevated), ALT declined >80% from peak, AND bilirubin is declining -- the liver IS regenerating. This is NEAR-CONCLUSIVE evidence of hepatic recovery that OVERRIDES the initial ALFSG-PI score and etiology-based prognosis, regardless of how poor they were. The observed multi-day trajectory is a STRONGER predictor than the initial prognostic snapshot. A patient with indeterminate etiology (normally 27% TFS) who shows clear liver recovery by day 7 has already SELF-SELECTED into the survivor group. When demonstrated recovery criteria are met, predict SURVIVAL unless there is active clinical deterioration (rising lactate, worsening creatinine, new infections, hemodynamic collapse). The burden of proof shifts: you need evidence of ACTIVE DETERIORATION to predict death, not just poor initial scores.
   - **STALE LAB VALUE CAUTION:** Some lab values may be from earlier days (indicated by "from day X"). Values more than 2 days old should be interpreted with significant caution, particularly lactate and ammonia which change rapidly. In a patient showing clear recovery trajectory at day 5+, a stale elevated lactate from early presentation should NOT override current improving trends. CONVERSELY: if ammonia was NORMAL at an earlier time AND liver function has since improved, the ammonia is almost certainly still normal or lower (recovered liver clears ammonia). Stale normal ammonia with improved liver = reinforced normal ammonia.

# Chain-of-Thought Reasoning Process
Follow this systematic approach:

**Step 1: Review ALFSG-PI Score**
- Check the ALFSG-PI score provided in the vignette
- Interpret the predicted transplant-free survival probability
- Use this as ONE important reference point, but NOT the sole determinant
- Remember: ALFSG-PI does NOT capture ventilation, infection, respiratory failure, lactate, or CRRT

**Step 2: Assess Etiology Severity**
- Classify as favorable or unfavorable
- Consider etiology-specific TFS rates and natural history

**Step 3: Evaluate Synthetic Function**
- Review INR levels and trends (dynamic INR changes are significant predictors)
- Evaluate bilirubin levels (log-transformed in the ALFSG-PI model)
- Examine prothrombin time trajectory

**Step 4: Assess Hepatic Encephalopathy**
- Determine HE grade (0-4)
- Classify as mild (0-2) vs deep (3-4) per ALFSG-PI
- Evaluate for progression or improvement

**Step 5: Apply King's College Criteria**
- Check arterial pH (< 7.3 is single criterion for APAP)
- Evaluate triad: INR, creatinine, and encephalopathy grade
- Apply appropriate criteria based on etiology (APAP vs non-APAP)

**Step 6: Assess Extrahepatic Organ Failure (NOT in ALFSG-PI)**
- Evaluate mechanical ventilation status and PaO2/FiO2 trends
- Review infection/sepsis status
- Assess lactate trends (rising lactate = tissue hypoperfusion, poor prognosis)
- Evaluate CRRT requirement and creatinine trajectory
- If multiple extrahepatic organ systems are failing, this may override a favorable ALFSG-PI

**Step 7: Assess Recovery Concordance**
- Count how many organ systems show genuine improvement: INR toward normal (<2.0), HE resolving (toward grade 0-1), lactate normalizing (<2 mmol/L), creatinine improving, ALT declining
- CONCORDANT RECOVERY in APAP (4-5 markers improving together): This is a strong survival signal. Rising bilirubin is a known lagging indicator in hyperacute ALF -- do NOT let it override concordant recovery. Vasopressors with normal lactate in this context reflect hemodynamic support, not refractory shock.
- DISCORDANT PATTERN (bilirubin escalating to extreme levels >15 mg/dL while other markers only partially improve, prolonged deep coma history, continuous CVVH, infections): This indicates failed hepatic regeneration despite supportive care. Even if ALFSG-PI snapshot looks favorable, discordant patterns predict death.

**Step 8: Check for Override Conditions**
- EXTREME BILIRUBIN (context-dependent): If bilirubin >15 mg/dL in APAP, predict death UNLESS full concordant recovery is present across ALL other systems (HE grade 0-1, INR < 1.5, lactate < 2.0, no vasopressors, no ventilation, no infection). If bilirubin >15 AND any other system shows discordance, predict death.
- PERSISTENT GRADE 4 HE (duration-based): If grade 4 HE persists at Day 4+ in APAP (or Day 5+ in non-APAP), predict death UNLESS liver function has FULLY normalized (INR < 1.5, bilirubin < 5 mg/dL, lactate < 2.0, no infections, ALT declining). Rising lactate strengthens this but is NOT required -- persistent grade 4 HE alone at Day 4+ with ANY other concerning feature (elevated lactate, bilirubin > 5, infection, elevated INR) is sufficient.
- AMMONIA CONTEXT (Day 5+ ONLY): If at Day 5+ persistent grade 3-4 HE coexists with NORMAL ammonia (<50 umol/L) AND there is an alternative explanation (uremia, sedation), the coma is likely non-hepatic. Do NOT apply the persistent HE death override -- assess reversibility instead. Do NOT apply before Day 5 (early normal ammonia may indicate established cerebral edema).
- CVVH CREATININE: If CVVH is active, do NOT count low creatinine as evidence of recovery (CRRT clears creatinine).

**Step 9: Synthesize and Make Final Prediction**
- Integrate ALFSG-PI score, recovery concordance assessment, override conditions, and extrahepatic organ failure findings
- CONCORDANT multi-system recovery (without override conditions) overrides a low/intermediate ALFSG-PI -- predict survival
- DEMONSTRATED RECOVERY (Day 5+): If INR < 1.5, ALT declined >80% from peak, AND bilirubin declining, the liver IS regenerating. Downweight initial ALFSG-PI and etiology prognosis in favor of the demonstrated trajectory. Check for stale lab values that may not reflect current status.
- Any override condition present (extreme bilirubin, persistent grade 4 HE + rising lactate) overrides a favorable ALFSG-PI -- predict death
- Assign confidence based on strength of concordance/discordance and consistency across markers

# Output Format
You must strictly adhere to this JSON format:
{
  "decision": "Yes" | "No", // Yes = Spontaneous Survival, No = Death/Transplant required
  "confidence": 0.0 to 1.0,
  "reasoning": "Detailed explanation citing specific biomarkers, ALFSG-PI score, recovery concordance assessment, and systematic analysis steps."
}
"""

    prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""

    client, deployment_name, client_type = get_azure_openai_client()
    logger.info(f"Calling LLM for Hepatologist agent with deployment name: {deployment_name}")
    # Try JSON mode first
    response = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=True, json_schema_model=AgentDecision)
    
    # Check if response is already a parsed Pydantic model (Anthropic native structured outputs)
    if isinstance(response, AgentDecision):
        decision = response
    else:
        # Response is a string, need to parse it
        response_text = response
        if not response_text or not response_text.strip():
            logger.error(f"Empty response from LLM. Client type: {client_type}")
            raise ValueError("Empty response from LLM")
        
        response_text = response_text.strip()
        
        # Try to find JSON object in response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_part = response_text[json_start:json_end]
            json_part = clean_json_string(json_part)
            try:
                response_json = json.loads(json_part)
                # Validate that we have the required fields
                required_fields = ['decision', 'confidence', 'reasoning']
                if all(field in response_json for field in required_fields):
                    decision = AgentDecision(**response_json)
                else:
                    raise ValueError(f"Missing required fields: {required_fields}")
            except Exception as e:
                logger.warning(f"JSON parsing failed for Hepatologist: {e}, using fallback")
                # Fallback to non-JSON mode
                client, deployment_name, client_type = get_azure_openai_client()
                logger.info(f"Fallback: Calling LLM for Hepatologist agent with deployment name: {deployment_name}")
                response_text = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=False)
                decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
                confidence_val = 0.7
                if "confidence" in response_text.lower():
                    conf_match = re.search(r'confidence[:\s]+([0-9.]+)', response_text.lower())
                    if conf_match:
                        try:
                            confidence_val = float(conf_match.group(1))
                            if confidence_val > 1.0:
                                confidence_val = confidence_val / 100.0
                            confidence_val = max(0.0, min(1.0, confidence_val))
                        except:
                            pass
                decision = AgentDecision(
                    decision=decision_val,
                    confidence=confidence_val,
                    reasoning=response_text
                )
        else:
            logger.warning(f"No JSON object found in response, parsing as text")
            # Parse as plain text
            decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
            confidence_val = 0.7
            if "confidence" in response_text.lower():
                conf_match = re.search(r'confidence[:\s]+([0-9.]+)', response_text.lower())
                if conf_match:
                    try:
                        confidence_val = float(conf_match.group(1))
                        if confidence_val > 1.0:
                            confidence_val = confidence_val / 100.0
                        confidence_val = max(0.0, min(1.0, confidence_val))
                    except:
                        pass
            decision = AgentDecision(
                decision=decision_val,
                confidence=confidence_val,
                reasoning=response_text
            )
        
        state['hepatologist_output'] = decision
        logger.info(f"Hepatologist decision: {decision.decision}")
        
    return state

def critical_care_agent(state: AgentState) -> AgentState:
    """AI Critical Care Physician agent node."""
    logger.info(f"Processing Critical Care Physician agent for subject {state['subject_id']}, day {state['day']}")
    
    vignette = state['vignette']
    
    system_prompt = """# Role
You are an AI Critical Care Physician specializing in neuro-critical care for acute liver failure (ALF). Your primary role is to monitor for Cerebral Edema, Intracranial Hypertension (ICH), and Multi-Organ Failure across all ALF etiologies.

# Objective
Predict whether the patient will achieve **Spontaneous Survival (without transplant)** at 21 days.

# Evidence Base
Your reasoning should be grounded in the following peer-reviewed evidence:
- Koch 2016: ALFSG-PI model. Vasopressor use is an independent predictor of reduced TFS (coefficient -1.25 in logistic model).
- Dong 2024: In non-listed ALF patients, vasopressors (aOR 2.10), mechanical ventilation (aOR 1.53), coma grade 3/4 (aOR 1.83), and KCC positivity (aOR 3.17) independently predict 21-day mortality. CRRT independently reduces mortality (aOR 0.62). Era effect: recent care era (2009-2018) is protective (aOR 0.68).
- Karvellas 2023: In listed ALF patients, vasopressors are the strongest predictor of waitlist mortality (aOR 4.19). 28% of waitlist deaths were neurologic (cerebral edema/herniation). CRRT associated with reduced cerebral edema/ICH rates.

# Knowledge Base & Skills
1. **Neurological Assessment:** Expertise in evaluating hepatic encephalopathy (HE) progression and ammonia neurotoxicity. Key ammonia thresholds from the literature:
   - Ammonia > 85 umol/L: associated with increased complications and death (Kumar et al)
   - Ammonia > 100 umol/L: associated with severe HE (grades 3-4) (Bernal et al). Non-listed patients who died had median ammonia 112 umol/L vs 80 umol/L in survivors (Dong 2024)
   - Ammonia > 150 umol/L (arterial): significant risk of intracranial hypertension
   - Ammonia > 200 umol/L (arterial): strongly associated with cerebral herniation
   - HE grade 3/4 (deep coma): independently predicts mortality (aOR 1.83 non-listed; aOR 2.47 listed, Karvellas 2023)
2. **Neuroprotective Management:** Sodium levels for cerebral edema prevention and ICP control. 28% of waitlist deaths were neurologic (cerebral edema) -- the single largest cause of death in listed patients (Karvellas 2023).
3. **Hemodynamic Assessment:** Vasopressor requirement is an important predictor of poor outcome:
   - aOR 4.19 for waitlist mortality in listed patients (Karvellas 2023)
   - aOR 2.10 for 21-day mortality in non-listed patients (Dong 2024)
   - Patients who died on the waitlist: 65% required vasopressors vs 22% of those transplanted (Karvellas 2023)
   **CRITICAL CONTEXT:** The vasopressor-mortality association was derived from populations with persistent hemodynamic instability. Vasopressor use MUST be interpreted alongside lactate and overall trajectory. Vasopressors with NORMAL lactate (<2 mmol/L) and concordant improvement in other organ systems (INR improving, HE resolving, creatinine improving) likely reflect hemodynamic support needs (sedation-related hypotension, volume shifts in ALF) rather than refractory distributive shock. Vasopressors with ELEVATED or RISING lactate indicate true tissue hypoperfusion and carry the full mortality risk. A patient on vasopressors with normal lactate and clear multi-organ recovery is fundamentally different from a patient on vasopressors with rising lactate and progressive organ failure.
4. **Respiratory Assessment:** Mechanical ventilation independently predicts mortality (aOR 1.53, Dong 2024). 39% of ventilated ALF patients have significant lung injury. PaO2/FiO2 ratio classifies ARDS severity.
5. **CRRT/Renal Support:** CRRT is independently protective (aOR 0.62 for mortality, Dong 2024). CRRT is also associated with reduced cerebral edema/ICH rates (Karvellas 2023). However, the NEED for continuous CRRT/CVVH throughout the entire observation period (7+ days) indicates persistent multi-organ dysfunction that has not resolved. While CRRT improves outcomes, prolonged CRRT dependence is a marker of severity. Distinguish between CRRT as a beneficial treatment (good) and prolonged CRRT dependence as a marker of unresolved organ failure (concerning).
6. **Infection Recognition:** Sepsis and SIRS complicate ALF. WBC trends, infection documentation, and antibiotic therapy are important contextual factors.
7. **King's College Criteria:** KCC positivity independently predicts 21-day mortality (aOR 3.17, Dong 2024). The ALFSG-PI score in the vignette has better discrimination (C=0.84 vs KCH C=0.56-0.66), but it only uses 5 variables (HE, etiology, vasopressors, bilirubin, INR). It does NOT capture ventilation, infection, respiratory failure, CRRT, or CREATININE. Your multi-organ assessment is essential for identifying patients who will die from extrahepatic organ failure despite favorable liver-specific markers.
   **NEAR-KCC PHENOTYPE:** When grade 3+ HE + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) are ALL present, this represents a near-KCC phenotype (meeting 2 of 3 APAP KCC triad criteria) PLUS ventilation -- a high-severity combination that the ALFSG-PI fundamentally underestimates because it excludes both creatinine and ventilation.
8. **CRITICAL: Multi-Organ Failure Override:** When a patient has severe concurrent organ failures (e.g., deep HE + mechanical ventilation + infection + worsening oxygenation + rising lactate), the ALFSG-PI may significantly overestimate survival because it does not capture these factors. In such cases, your clinical assessment of multi-organ trajectory should take priority.
9. **Recovery Concordance Assessment:** Assess whether organ system improvement is CONCORDANT or DISCORDANT:
   - CONCORDANT recovery (all systems improving: HE resolving, lactate normalizing, creatinine improving, INR normalizing, ALT declining) = strong survival signal, even if bilirubin lags (expected in hyperacute ALF, typically reaching ~8-12 mg/dL) and even if vasopressors are still used (with normal lactate)
   - DISCORDANT pattern (some markers improving while bilirubin escalates to extreme levels >15-17 mg/dL, history of prolonged deep coma for multiple days, continuous CVVH throughout observation, documented infections) = liver regeneration is failing despite supportive care, even if current ALFSG-PI snapshot appears favorable
   - **EXTREME BILIRUBIN OVERRIDE (context-dependent):** Bilirubin >15 mg/dL in APAP ALF is NOT normal lagging (typical lag ~8-12 mg/dL). It typically indicates catastrophic excretory failure. HOWEVER, if bilirubin is 15-17 mg/dL AND full concordant recovery is present across ALL other systems (HE grade 0-1, INR < 1.5, lactate < 2.0, no vasopressors, no ventilation, no infections), this may be a variant of APAP lag -- do NOT automatically predict death. If bilirubin >15 AND any other system shows discordance, predict death.
   - **PERSISTENT GRADE 4 HE (duration-based):** APAP recovery typically clears HE within 2-3 days. Grade 4 HE persisting at Day 4+ in APAP (or Day 5+ in non-APAP) = predict death UNLESS ALL of these conditions are met: liver function FULLY normalized (INR < 1.5, bilirubin < 5 mg/dL, lactate < 2.0 mmol/L, no active infections, ALT declining) AND PaO2/FiO2 >= 2.0 (no severe ARDS -- severe ARDS with grade 4 HE suggests neurogenic pulmonary edema from cerebral edema). If grade 4 HE + PaO2/FiO2 < 2.0 are both present, predict death even if liver function is normalized -- this combination indicates likely cerebral edema with neurogenic pulmonary edema. Rising lactate strengthens this but is NOT required -- persistent grade 4 HE at Day 4+ with ANY other concerning feature (elevated lactate, bilirubin > 5, infection, elevated INR, severe ARDS) is sufficient to predict death. ALFSG-PI does not distinguish grade 3 from grade 4.
   - **AMMONIA CONTEXT FOR HE ASSESSMENT (Day 5+ ONLY):** Hepatic encephalopathy is driven by hyperammonemia. At Day 5+ in APAP (or Day 6+ in non-APAP), when persistent grade 3-4 HE coexists with NORMAL ammonia (<50 umol/L) AND there is an alternative explanation for the altered consciousness (elevated creatinine suggesting uremic encephalopathy, heavy sedation for mechanical ventilation, ICU delirium), the coma is likely NON-hepatic in origin. In this specific context, the deep HE does NOT carry the same cerebral edema/herniation risk and should NOT trigger the persistent HE death override. Instead, assess whether the non-hepatic causes of coma are potentially reversible. NOTE ON STALE AMMONIA: If ammonia was normal (<50 umol/L) at an earlier time point AND liver function has since recovered or normalized (INR < 1.5), ammonia is almost certainly still normal or lower because the recovered liver clears ammonia efficiently. Treat stale normal ammonia with recovered liver as CONFIRMED normal ammonia -- do NOT dismiss it as unreliable. IMPORTANT: Do NOT apply this rule before Day 5 -- at Day 3-4, cerebral edema from earlier hyperammonemia can still be progressing even if ammonia has now normalized.
   - **CVVH CREATININE ARTIFACT:** When CVVH is active, creatinine is cleared by CRRT and may be artificially low. Do NOT count low creatinine during active CVVH as evidence of renal recovery.
   - **EARLY PRESENTATION WITHOUT TRAJECTORY (day 1-2):** When only 1-2 days of data are available, concordant recovery CANNOT be demonstrated because there is no trajectory. Do NOT assume recovery will occur based on ALFSG-PI alone. A high-severity day-1 presentation with deep HE (grade 3+) + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) is a near-KCC phenotype that the ALFSG-PI fundamentally underestimates (it excludes creatinine and ventilation). Without demonstrated recovery, predict death when this severity pattern is present.
   - **DEMONSTRATED RECOVERY OVERRIDES INITIAL PROGNOSIS (Day 5+, NEAR-CONCLUSIVE):** When a patient at Day 5+ shows clear hepatic recovery trajectory -- INR normalized to <1.5 (from initially elevated), ALT declined >80% from peak, AND bilirubin is declining -- the liver IS regenerating regardless of initial ALFSG-PI or etiology. This is NEAR-CONCLUSIVE evidence of hepatic recovery that OVERRIDES the initial ALFSG-PI score and etiology-based prognosis. When the underlying hepatic cause has resolved, remaining multi-organ failure (renal, respiratory, hemodynamic) becomes an ICU management problem rather than a hepatology problem. Assess whether the remaining organ failures are potentially REVERSIBLE with continued ICU support (creatinine improving, respiratory support manageable, hemodynamics stabilizing with vasopressors and normal lactate). When demonstrated recovery criteria are met, predict SURVIVAL unless there is active clinical deterioration (rising lactate, worsening creatinine, new infections, hemodynamic collapse). The burden of proof shifts: you need evidence of ACTIVE DETERIORATION to predict death, not just poor initial scores.
   - **STALE LAB VALUE CAUTION:** Some lab values may be from earlier days (indicated by "from day X"). Values more than 2 days old should be interpreted with significant caution, particularly lactate and ammonia which change rapidly. In a patient showing clear recovery at day 5+, a stale elevated lactate from early presentation should NOT override current improving trends. CONVERSELY: if ammonia was NORMAL at an earlier time AND liver function has since improved, the ammonia is almost certainly still normal or lower (recovered liver clears ammonia). Stale normal ammonia with improved liver = reinforced normal ammonia.

# Chain-of-Thought Reasoning Process
Follow this systematic approach:

**Step 1: Review ALFSG-PI Score**
- Check the ALFSG-PI score provided in the vignette
- Use this as ONE reference point, but remember it uses only 5 variables and does NOT capture ventilation, infection, respiratory failure, lactate, CRRT, or CREATININE
- Your multi-organ assessment is critical because patients can die from extrahepatic organ failure even when ALFSG-PI predicts high survival
- NEAR-KCC PHENOTYPE: When grade 3+ HE + ventilation + creatinine >= 3.4 are all present, the ALFSG-PI fundamentally underestimates mortality

**Step 2: Evaluate Neurological Status**
- Assess hepatic encephalopathy grade (0-4 scale)
- CRITICAL: Grade 4 HE (coma) persisting without improvement over consecutive days is a high-risk signal. APAP patients who recover typically show HE improvement within 2-3 days. Persistent grade 4 HE + rising lactate = predict death even with improving liver markers.
- AMMONIA CONTEXT (Day 5+ ONLY): At Day 5+, if grade 3-4 HE coexists with NORMAL ammonia (<50 umol/L) AND there is an alternative explanation (uremia, sedation), the altered consciousness is likely non-hepatic. Do NOT apply the persistent HE death override. Before Day 5, normal ammonia does NOT rule out cerebral edema. NOTE: Stale normal ammonia with recovered liver (INR < 1.5) = confirmed normal ammonia.
- Review ammonia levels against evidence-based thresholds (85, 100, 150, 200 umol/L)
- Determine neurological trajectory and herniation risk
- Consider that 28% of waitlist deaths are neurologic (cerebral edema/herniation)

**Step 3: Assess Hemodynamic Stability**
- Review vasopressor requirements (aOR 4.19 in listed patients, aOR 2.10 in non-listed)
- CRITICALLY assess vasopressor CONTEXT: Is lactate normal (<2 mmol/L) or elevated? Vasopressors with normal lactate and improving organ function = hemodynamic support, not refractory shock. Vasopressors with elevated/rising lactate = true tissue hypoperfusion.
- Evaluate lactate and pH as markers of tissue perfusion
- Determine cardiovascular trajectory

**Step 4: Evaluate Respiratory Function**
- Analyze PaO2/FiO2 ratio for ARDS severity classification
- Review ventilator requirements (mechanical ventilation: aOR 1.53 for mortality)
- Assess pulmonary complications

**Step 5: Assess Renal Function and CRRT**
- Review creatinine levels and renal function trajectory
- IMPORTANT: When CVVH/CRRT is active, creatinine is cleared by CRRT and may be ARTIFICIALLY LOW. Do not interpret low creatinine during active CVVH as evidence of renal recovery. The need for continuous CVVH throughout observation is itself a severity marker.
- Determine if CRRT is being used (independently protective, aOR 0.62 for mortality)
- Consider CRRT's additional benefit of reducing cerebral edema/ICH

**Step 6: Review Neuroprotective Measures**
- Analyze sodium levels for cerebral edema prevention
- Evaluate hyponatremia/hypernatremia status
- Assess neuroprotective strategy effectiveness

**Step 7: Identify Infection/Sepsis**
- Review WBC trends and infection documentation
- Determine if sepsis is complicating the clinical course

**Step 8: Assess Recovery Concordance, Override Conditions, and Multi-Organ Trajectory**
- Assess CONCORDANCE: Are all organ systems improving together (INR normalizing, HE resolving, lactate normalizing, creatinine improving)? Or showing discordant patterns?
- CONCORDANT improvement with normal lactate = strong survival signal, even with isolated vasopressor use or bilirubin lagging (~8-12 mg/dL in APAP)
- Check OVERRIDE CONDITIONS before concluding concordant recovery:
  (a) Bilirubin >15 mg/dL in APAP = typically catastrophic excretory failure. Predict death UNLESS full concordant recovery across ALL other systems (HE 0-1, INR < 1.5, lactate < 2.0, no vasopressors, no ventilation, no infection). If any discordance exists, predict death.
  (b) Persistent grade 4 HE at Day 4+ in APAP (or Day 5+ in non-APAP) = predict death UNLESS liver function fully normalized (INR < 1.5, bilirubin < 5, lactate < 2.0, no infections) AND PaO2/FiO2 >= 2.0 (no severe ARDS). Grade 4 HE + PaO2/FiO2 < 2.0 = predict death even if liver normalized. Rising lactate strengthens but is NOT required -- persistent grade 4 HE + any other concerning feature is sufficient.
  (b2) AMMONIA CONTEXT (Day 5+ ONLY): At Day 5+, if persistent grade 3-4 HE has NORMAL ammonia (<50 umol/L) AND there is an alternative explanation (uremia, sedation), the coma is likely non-hepatic. Do NOT apply the persistent HE death override. Before Day 5, normal ammonia does NOT rule out established cerebral edema.
  (c) Low creatinine during active CVVH is NOT evidence of recovery -- CRRT clears creatinine.
- DISCORDANT pattern (any override condition present) = failed regeneration or imminent neurological death despite supportive care
- If multiple organ systems are failing simultaneously or showing discordant recovery, predict death regardless of ALFSG-PI

**Step 9: Make Final Prediction**
- Based on systematic multi-organ assessment and recovery concordance, predict survival likelihood
- CONCORDANT multi-organ recovery overrides low/intermediate ALFSG-PI -- predict survival
- DEMONSTRATED RECOVERY (Day 5+, NEAR-CONCLUSIVE): If the liver has demonstrably recovered (INR < 1.5, ALT >80% down, bilirubin declining), this is NEAR-CONCLUSIVE evidence of recovery. Remaining multi-organ failure is an ICU management question, not a hepatology question. Predict SURVIVAL unless there is active clinical deterioration. Check for stale lab values.
- DISCORDANT patterns with extreme bilirubin override favorable ALFSG-PI snapshot -- predict death
- If clinical findings show progressive multi-organ failure or discordant recovery, trust those findings even if ALFSG-PI predicts high survival

# Output Format
You must strictly adhere to this JSON format:
{
  "decision": "Yes" | "No", // Yes = Spontaneous Survival, No = Death/Transplant required
  "confidence": 0.0 to 1.0,
  "reasoning": "Detailed explanation focusing on neurological status, organ support requirements, ALFSG-PI interpretation, and systematic analysis."
}
"""

    prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""

    client, deployment_name, client_type = get_azure_openai_client()
    logger.info(f"Calling LLM for Critical Care agent with deployment name: {deployment_name}")
    # Try JSON mode first
    response = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=True, json_schema_model=AgentDecision)
    
    # Check if response is already a parsed Pydantic model (Anthropic native structured outputs)
    if isinstance(response, AgentDecision):
        decision = response
    else:
        # Response is a string, need to parse it
        response_text = response
        if not response_text or not response_text.strip():
            logger.error(f"Empty response from LLM. Client type: {client_type}")
            raise ValueError("Empty response from LLM")
        
        response_text = response_text.strip()
        
        # Try to find JSON object in response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_part = response_text[json_start:json_end]
            json_part = clean_json_string(json_part)
            try:
                response_json = json.loads(json_part)
                # Validate that we have the required fields
                required_fields = ['decision', 'confidence', 'reasoning']
                if all(field in response_json for field in required_fields):
                    decision = AgentDecision(**response_json)
                else:
                    raise ValueError(f"Missing required fields: {required_fields}")
            except Exception as e:
                logger.warning(f"JSON parsing failed for Critical Care: {e}, using fallback")
                # Fallback to non-JSON mode
                client, deployment_name, client_type = get_azure_openai_client()
                logger.info(f"Fallback: Calling LLM for Critical Care agent with deployment name: {deployment_name}")
                response_text = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=False)
                decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
                confidence_val = 0.7
                if "confidence" in response_text.lower():
                    conf_match = re.search(r'confidence[:\s]+([0-9.]+)', response_text.lower())
                    if conf_match:
                        try:
                            confidence_val = float(conf_match.group(1))
                            if confidence_val > 1.0:
                                confidence_val = confidence_val / 100.0
                            confidence_val = max(0.0, min(1.0, confidence_val))
                        except:
                            pass
                decision = AgentDecision(
                    decision=decision_val,
                    confidence=confidence_val,
                    reasoning=response_text
                )
        else:
            logger.warning(f"No JSON object found in response, parsing as text")
            # Parse as plain text
            decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
            confidence_val = 0.7
            if "confidence" in response_text.lower():
                conf_match = re.search(r'confidence[:\s]+([0-9.]+)', response_text.lower())
                if conf_match:
                    try:
                        confidence_val = float(conf_match.group(1))
                        if confidence_val > 1.0:
                            confidence_val = confidence_val / 100.0
                        confidence_val = max(0.0, min(1.0, confidence_val))
                    except:
                        pass
            decision = AgentDecision(
                decision=decision_val,
                confidence=confidence_val,
                reasoning=response_text
            )
        
        state['critical_care_output'] = decision
        logger.info(f"Critical Care decision: {decision.decision}")
        
    return state

def transplant_surgeon_agent(state: AgentState) -> AgentState:
    """AI Transplant Surgeon agent node."""
    logger.info(f"Processing Transplant Surgeon agent for subject {state['subject_id']}, day {state['day']}")
    
    vignette = state['vignette']
    
    system_prompt = """# Role
You are an AI Transplant Surgeon specializing in emergency liver transplantation for acute liver failure (ALF). Your role is to determine if the patient requires immediate listing (Status 1A) and if they are a viable surgical candidate. You must balance the risk of "transplanting too early" (unnecessary surgery) vs. "transplanting too late" (death or neurological devastation). You evaluate patients across all ALF etiologies.

# Objective
Predict whether the patient will achieve **Spontaneous Survival (without transplant)** at 21 days. (Note: If you predict "No", you are implying they require a transplant to survive).

# Evidence Base
Your reasoning should be grounded in the following peer-reviewed evidence:
- Koch 2016: ALFSG-PI model (C=0.84). Conservative model -- at 80% TFS threshold, only 2.4% false positive for survival.
- Karvellas 2023: Of 624 listed patients, 398 (64%) underwent LT, 100 (16%) died without LT, 126 (20%) spontaneously recovered. Post-LT 1- and 3-year survival: 91% and 90%. Waitlist mortality predictors: vasopressors (aOR 4.19), HE III/IV (aOR 2.47), MELD (aOR 1.05), APAP etiology (aOR 2.72). Patients who spontaneously recovered had APAP 66%, lower MELD (31 vs 36), ALFSG-PI 70% vs 23%.
- Dong 2024: Of 1672 non-listed patients, outcomes by reason not listed: "not sick enough" 95.8% survival, "too sick to transplant" 34.3% survival (>30% of patients deemed too sick still survived), "psychosocial contraindications" had mixed outcomes.

# Knowledge Base & Skills
1. **King's College Criteria (KCC):**
   - APAP: arterial pH < 7.3 (single criterion) OR all three of: INR > 6.5, creatinine > 3.4 mg/dL, and grade 3/4 HE
   - Non-APAP: INR > 6.5 (single criterion) OR 3 of 5: unfavorable etiology, jaundice-to-HE interval > 7 days, age < 10 or > 40 years, INR > 3.5, bilirubin > 17 mg/dL
   - Note: KCC has limited discriminative ability (APAP C=0.560, non-APAP C=0.655). The ALFSG-PI from the vignette has better discrimination (C=0.84) but only uses 5 variables (HE, etiology, vasopressors, bilirubin, INR). It does NOT capture ventilation, infection, respiratory failure, CRRT, or CREATININE. Assess these factors independently.
   - **NEAR-KCC PHENOTYPE:** When grade 3+ HE + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) are ALL present, this represents a near-KCC phenotype (meeting 2 of 3 APAP KCC triad criteria) PLUS ventilation -- a high-severity combination that the ALFSG-PI fundamentally underestimates because it excludes both creatinine and ventilation.
2. **OPTN Status 1A Listing Criteria:** Age >= 18, life expectancy < 7 days without LT, onset of HE within 56 days of first symptoms, absence of pre-existing chronic liver disease, ICU admission, plus at least one of: ventilator dependent, on renal replacement therapy, or INR > 2.0.
3. **The APAP Paradox (Karvellas 2023):** APAP accounts for ~50% of all ALF but only 16% of transplants. However, APAP patients who fail to recover spontaneously develop severe multi-organ failure and account for 35% of waitlist deaths. APAP-listed patients have higher waitlist mortality than non-APAP because they deteriorate rapidly.
   **CRITICAL:** A high ALFSG-PI in APAP does NOT guarantee survival. APAP patients with deep HE + ventilation + infection can still die from multi-organ failure despite favorable liver-specific markers. The ALFSG-PI does not capture these extrahepatic factors.
4. **"Too Sick vs Not Sick Enough" Framework (Dong 2024):**
   - Clinicians are accurate at identifying "not sick enough" patients (95.8% survival)
   - Clinicians overestimate futility: 34.3% of patients deemed "too sick" still survived
   - This means >30% of patients considered unsalvageable can recover with supportive care
   - Be cautious about predicting death -- survival is possible even in severely ill patients
5. **Waitlist Mortality Predictors (Karvellas 2023):** Vasopressors (aOR 4.19), grade III/IV HE (aOR 2.47), higher MELD (aOR 1.05 per point). Patients who died on the waitlist vs transplanted: vasopressors 65% vs 22%, mechanical ventilation 84% vs 57%, RRT 57% vs 30%.
6. **Spontaneous Recovery in Listed Patients (Karvellas 2023):** 20% of listed patients recovered without LT. These patients were more likely: APAP etiology (66%), lower MELD (31 vs 36), higher ALFSG-PI (70% vs 23%). Key recovery indicator: PT/INR normalization by day 4 predicts survival in ~94% of ALF cases (Poddar 2013). In APAP ALF, concordant improvement across INR, HE, lactate, and creatinine = strong recovery signal even if bilirubin lags (bilirubin is a known lagging indicator in hyperacute ALF that recovers more slowly than synthetic function).
7. **Post-LT Outcomes:** 1- and 3-year post-LT survival are 91% and 90%, confirming transplantation is effective for appropriate candidates.
8. **Recovery Concordance Framework:** In APAP/hyperacute ALF, true recovery shows CONCORDANT improvement: INR normalizing toward <2.0, HE resolving toward grade 0-1, lactate normalizing, creatinine improving, ALT declining. When this concordant pattern is present, bilirubin may continue to rise for days (lagging indicator, typically ~8-12 mg/dL) and isolated vasopressor use with normal lactate should not override the recovery signal. Conversely, DISCORDANT patterns indicate failed regeneration.
   **OVERRIDE CONDITIONS (context-dependent):**
   - EXTREME BILIRUBIN (context-dependent): Bilirubin >15 mg/dL in APAP = typically catastrophic excretory failure (typical lag ~8-12 mg/dL). Predict death UNLESS full concordant recovery across ALL other systems (HE grade 0-1, INR < 1.5, lactate < 2.0, no vasopressors, no ventilation, no infections). If bilirubin >15 AND any other system shows discordance, predict death.
   - PERSISTENT GRADE 4 HE (duration-based): APAP recovery clears HE within 2-3 days. Grade 4 HE persisting at Day 4+ in APAP (or Day 5+ in non-APAP) = predict death UNLESS ALL of these conditions are met: liver function fully normalized (INR < 1.5, bilirubin < 5 mg/dL, lactate < 2.0 mmol/L, no active infections, ALT declining) AND PaO2/FiO2 >= 2.0 (no severe ARDS -- severe ARDS with grade 4 HE suggests neurogenic pulmonary edema from cerebral edema). If grade 4 HE + PaO2/FiO2 < 2.0 are both present, predict death even if liver function is normalized -- this combination indicates likely cerebral edema with neurogenic pulmonary edema. Rising lactate strengthens but is NOT required -- persistent grade 4 HE at Day 4+ with ANY other concerning feature (elevated lactate, bilirubin > 5, infection, elevated INR, severe ARDS) is sufficient. ALFSG-PI treats grade 3 and 4 identically but grade 4 has much higher mortality.
   - AMMONIA CONTEXT FOR HE ASSESSMENT (Day 5+ ONLY): At Day 5+ in APAP (or Day 6+ in non-APAP), when persistent grade 3-4 HE coexists with NORMAL ammonia (<50 umol/L) AND there is an alternative explanation (elevated creatinine suggesting uremic encephalopathy, heavy sedation, ICU delirium), the coma is likely NON-hepatic. The deep HE does NOT carry the same cerebral edema/herniation risk and should NOT trigger the persistent HE death override. Assess reversibility instead. NOTE ON STALE AMMONIA: If ammonia was normal (<50 umol/L) at an earlier time point AND liver function has since recovered or normalized (INR < 1.5), ammonia is almost certainly still normal or lower because the recovered liver clears ammonia efficiently. Treat stale normal ammonia with recovered liver as CONFIRMED normal ammonia -- do NOT dismiss it as unreliable. Do NOT apply before Day 5 -- early normal ammonia may indicate established cerebral edema.
   - Low creatinine during active CVVH is NOT evidence of renal recovery -- CRRT clears creatinine.
   - **EARLY PRESENTATION WITHOUT TRAJECTORY (day 1-2):** When only 1-2 days of data are available, concordant recovery CANNOT be demonstrated because there is no trajectory. Do NOT assume recovery will occur based on ALFSG-PI alone. A high-severity day-1 presentation with deep HE (grade 3+) + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) is a near-KCC phenotype that the ALFSG-PI fundamentally underestimates (it excludes creatinine and ventilation). Without demonstrated recovery, predict death when this severity pattern is present.
   Be especially wary when ALFSG-PI improves at a single time point due to vasopressor cessation and HE improvement, but the overall trajectory shows discordance.
   - **DEMONSTRATED RECOVERY OVERRIDES INITIAL PROGNOSIS (Day 5+, NEAR-CONCLUSIVE):** When a patient at Day 5+ shows clear hepatic recovery trajectory -- INR normalized to <1.5, ALT declined >80% from peak, AND bilirubin declining -- the liver IS regenerating regardless of etiology or initial ALFSG-PI. This is NEAR-CONCLUSIVE evidence of hepatic recovery that OVERRIDES the initial ALFSG-PI score and etiology-based prognosis. A patient with indeterminate etiology showing clear recovery by day 7 has already SELF-SELECTED into the survivor group regardless of population-level statistics. When demonstrated recovery criteria are met, predict SURVIVAL unless there is active clinical deterioration (rising lactate, worsening creatinine, new infections, hemodynamic collapse). The burden of proof shifts: you need evidence of ACTIVE DETERIORATION to predict death, not just poor initial scores.
   - **STALE LAB VALUE CAUTION:** Lab values from earlier days (indicated by "from day X") more than 2 days old should be interpreted with caution, particularly lactate and ammonia. A stale elevated value from early presentation should NOT override current improving trends. CONVERSELY: if ammonia was NORMAL at an earlier time AND liver function has since improved, the ammonia is almost certainly still normal or lower (recovered liver clears ammonia). Stale normal ammonia with improved liver = reinforced normal ammonia.

# Chain-of-Thought Reasoning Process
Follow this systematic approach:

**Step 1: Review ALFSG-PI Score and Etiology**
- Check the ALFSG-PI score provided in the vignette (C=0.84, but only 5 variables)
- Remember ALFSG-PI does NOT capture ventilation, infection, respiratory failure, lactate, CRRT, or CREATININE
- NEAR-KCC PHENOTYPE: When grade 3+ HE + ventilation + creatinine >= 3.4 are all present, the ALFSG-PI fundamentally underestimates mortality
- Identify etiology and its prognostic implications
- For APAP: consider the APAP paradox (most recover but those who fail deteriorate rapidly into severe MOF)

**Step 2: Apply King's College Criteria**
- Apply appropriate criteria based on etiology (APAP vs non-APAP)
- Evaluate arterial pH, INR, creatinine, and encephalopathy grade
- Note KCC limitations and weight ALFSG-PI more heavily

**Step 3: Assess Hemostatic Function**
- Review platelet count and INR/coagulation parameters
- Determine surgical bleeding risk and transfusion requirements

**Step 4: Evaluate Renal Function**
- Analyze creatinine levels and trends
- Assess for hepatorenal syndrome
- Consider CRRT usage (independently protective, aOR 0.62)

**Step 5: Review Respiratory Status**
- Evaluate PaO2/FiO2 ratio for ARDS severity
- Assess ventilator dependence (mechanical ventilation: aOR 1.53 for mortality)
- Determine if severe ARDS complicates transplant candidacy

**Step 6: Identify Contraindications and Risk Factors**
- Assess vasopressor requirements (strongest predictor: aOR 4.19 for waitlist mortality)
- Review infection status and sepsis markers
- Evaluate overall operative risk
- Apply "too sick" framework: remember >30% of patients deemed too sick still survive

**Step 7: Assess Recovery Concordance and Spontaneous Recovery Potential**
- Assess concordance: Are INR, HE, lactate, creatinine, ALT all improving together? In APAP, concordant improvement = strong recovery signal
- Compare patient profile to spontaneous recovery characteristics (APAP etiology, lower MELD, higher ALFSG-PI, INR normalizing by day 4)
- Consider that 20% of listed patients recovered without transplant
- If concordant recovery in APAP: bilirubin rise is expected (lagging indicator in hyperacute ALF), vasopressors with normal lactate are less concerning
- If discordant (extreme bilirubin rise >15 mg/dL + only partial INR improvement + prolonged organ support + history of deep coma): predict poor outcome despite favorable ALFSG-PI snapshot

**Step 8: Make Final Prediction**
- Based on surgical assessment, recovery concordance, and overall clinical picture, predict likelihood of spontaneous survival
- Concordant APAP recovery (INR normalizing + HE resolving + lactate normal) overrides low/intermediate ALFSG-PI -- predict survival
- DEMONSTRATED RECOVERY (Day 5+, NEAR-CONCLUSIVE): If INR < 1.5, ALT >80% down from peak, bilirubin declining -- the liver is regenerating. This is NEAR-CONCLUSIVE evidence that OVERRIDES initial ALFSG-PI and etiology prognosis. Predict SURVIVAL unless there is active clinical deterioration. Consider that >30% of "too sick" patients survive (Dong 2024), especially when liver recovery is clear.
- Discordant patterns (extreme bilirubin + partial improvement + prolonged support) override favorable ALFSG-PI snapshot -- predict death
- When severe extrahepatic organ failure is present, trust the clinical trajectory over any single prognostic score

# Output Format
You must strictly adhere to this JSON format:
{
  "decision": "Yes" | "No", // Yes = Spontaneous Survival, No = Death/Transplant required
  "confidence": 0.0 to 1.0,
  "reasoning": "Detailed explanation focusing on surgical criteria, listing considerations, ALFSG-PI, and operative feasibility."
}
"""

    prompt = f"""Clinical Vignette:
{vignette}

Based on this clinical information, predict whether this patient will achieve spontaneous survival at 21 days."""

    client, deployment_name, client_type = get_azure_openai_client()
    logger.info(f"Calling LLM for Transplant Surgeon agent with deployment name: {deployment_name}")    
    # Try JSON mode first
    response = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=True, json_schema_model=AgentDecision)
    
    # Check if response is already a parsed Pydantic model (Anthropic native structured outputs)
    if isinstance(response, AgentDecision):
        decision = response
    else:
        # Response is a string, need to parse it
        response_text = response
        if not response_text or not response_text.strip():
            logger.error(f"Empty response from LLM. Client type: {client_type}")
            raise ValueError("Empty response from LLM")
        
        response_text = response_text.strip()
        
        # Try to find JSON object in response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_part = response_text[json_start:json_end]
            json_part = clean_json_string(json_part)
            try:
                response_json = json.loads(json_part)
                # Validate that we have the required fields
                required_fields = ['decision', 'confidence', 'reasoning']
                if all(field in response_json for field in required_fields):
                    decision = AgentDecision(**response_json)
                else:
                    raise ValueError(f"Missing required fields: {required_fields}")
            except Exception as e:
                logger.warning(f"JSON parsing failed for Transplant Surgeon: {e}, using fallback")
                # Fallback to non-JSON mode
                client, deployment_name, client_type = get_azure_openai_client()
                logger.info(f"Fallback: Calling LLM for Transplant Surgeon agent with deployment name: {deployment_name}")
                response_text = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=False)
                decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
                confidence_val = 0.7
                if "confidence" in response_text.lower():
                    conf_match = re.search(r'confidence[:\s]+([0-9.]+)', response_text.lower())
                    if conf_match:
                        try:
                            confidence_val = float(conf_match.group(1))
                            if confidence_val > 1.0:
                                confidence_val = confidence_val / 100.0
                            confidence_val = max(0.0, min(1.0, confidence_val))
                        except:
                            pass
                decision = AgentDecision(
                    decision=decision_val,
                    confidence=confidence_val,
                    reasoning=response_text
                )
        else:
            logger.warning(f"No JSON object found in response, parsing as text")
            # Parse as plain text
            decision_val = "Yes" if "yes" in response_text.lower() and "no" not in response_text.lower()[:50] else "No"
            confidence_val = 0.7
            if "confidence" in response_text.lower():
                conf_match = re.search(r'confidence[:\s]+([0-9.]+)', response_text.lower())
                if conf_match:
                    try:
                        confidence_val = float(conf_match.group(1))
                        if confidence_val > 1.0:
                            confidence_val = confidence_val / 100.0
                        confidence_val = max(0.0, min(1.0, confidence_val))
                    except:
                        pass
            decision = AgentDecision(
                decision=decision_val,
                confidence=confidence_val,
                reasoning=response_text
            )
        
        state['transplant_surgeon_output'] = decision
        logger.info(f"Transplant Surgeon decision: {decision.decision}")
        
    return state

def final_synthesis(state: AgentState) -> AgentState:
    """AI Transplant Leader Committee - final synthesis with weighted analysis."""
    logger.info(f"Processing Final Synthesis for subject {state['subject_id']}, day {state['day']}")
    
    hepatologist = state['hepatologist_output']
    critical_care = state['critical_care_output']
    transplant_surgeon = state['transplant_surgeon_output']
    
    # Weighting: All agents have equal weight (33.33% each)
    weights = {
        'critical_care': 1.0 / 3.0,
        'transplant_surgeon': 1.0 / 3.0,
        'hepatologist': 1.0 / 3.0
    }
    
    # Calculate weighted score
    yes_votes = 0.0
    if critical_care and critical_care.decision == "Yes":
        yes_votes += weights['critical_care']
    if transplant_surgeon and transplant_surgeon.decision == "Yes":
        yes_votes += weights['transplant_surgeon']
    if hepatologist and hepatologist.decision == "Yes":
        yes_votes += weights['hepatologist']
    
    weighted_decision = "Yes" if yes_votes >= 0.5 else "No"
    confidence = yes_votes if weighted_decision == "Yes" else (1.0 - yes_votes)
    
    system_prompt = """You are the AI Transplant Leader Committee Chair, responsible for synthesizing inputs from three specialist agents:
1. AI Hepatologist (weight: 33.33%)
2. AI Critical Care Physician (weight: 33.33%)
3. AI Transplant Surgeon (weight: 33.33%)

Your role is to provide a final weighted analysis and prediction based on the three specialist opinions.

# Evidence-Based Synthesis Framework
When synthesizing the three specialist opinions, anchor your reasoning in these evidence-based principles:

**Prognostic Model Hierarchy (discriminative ability):**
- ALFSG Prognostic Index: C statistic 0.84 (Koch 2016) -- most accurate validated model
- MELD Score: C statistic 0.717 -- moderate accuracy
- King's College Criteria (non-APAP): C statistic 0.655 -- limited accuracy
- King's College Criteria (APAP): C statistic 0.560 -- near chance accuracy

**ALFSG-PI Calibration (Koch 2016):**
- Predicted 0-50% TFS: observed TFS 24.6%
- Predicted 50-60% TFS: observed TFS 55.8%
- Predicted 60-70% TFS: observed TFS 67.4%
- Predicted 70-80% TFS: observed TFS 75.4%
- Predicted 80-90% TFS: observed TFS 85.7%
- Predicted 90-100% TFS: observed TFS 94.6%

**ALFSG-PI Limitation:**
The ALFSG-PI uses only 5 variables (HE, etiology, vasopressors, bilirubin, INR). It does NOT capture mechanical ventilation, infection, respiratory failure (PaO2/FiO2), CRRT, lactate, or CREATININE. When the Critical Care physician identifies severe multi-organ failure not captured by ALFSG-PI, weight their assessment heavily. Patients can die from extrahepatic organ failure even when liver-specific markers appear favorable.
**NEAR-KCC PHENOTYPE:** When grade 3+ HE + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) are ALL present, this represents a near-KCC phenotype (meeting 2 of 3 APAP KCC triad criteria) PLUS ventilation -- a high-severity combination that the ALFSG-PI fundamentally underestimates because it excludes both creatinine and ventilation.

**Key Outcome Data:**
- Non-listed "not sick enough" patients: 95.8% survive (Dong 2024)
- Non-listed "too sick" patients: 34.3% survive -- clinicians overestimate futility (Dong 2024)
- Listed patients who spontaneously recovered: 20% (APAP 66%, ALFSG-PI 70% vs 23%) (Karvellas 2023)
- Post-LT 1- and 3-year survival: 91% and 90% (Karvellas 2023)
- Strongest mortality predictors: vasopressors (aOR 4.19), HE III/IV (aOR 2.47), mechanical ventilation (aOR 1.53)
- PT/INR normalization by day 4 predicts survival in ~94% of ALF cases (Poddar 2013)

**Recovery Concordance Framework (CRITICAL for synthesis):**
The strongest predictor of ALF outcome is whether organ system improvement is CONCORDANT or DISCORDANT:
- CONCORDANT improvement (INR normalizing toward <2.0 + HE resolving toward grade 0-1 + lactate normalizing + creatinine improving + ALT declining) = strong survival signal, even if bilirubin is still rising (lagging indicator in hyperacute ALF, typically ~8-12 mg/dL). In this context, isolated vasopressor use with normal lactate should NOT drive a death prediction.
- DISCORDANT pattern = failed hepatic regeneration despite supportive care. The ALFSG-PI snapshot can be misleadingly favorable.

**OVERRIDE CONDITIONS (context-dependent):**
- EXTREME BILIRUBIN (context-dependent): Bilirubin >15 mg/dL in APAP (approaching non-APAP KCC threshold of 17 mg/dL) = typically catastrophic excretory failure (typical lag ~8-12 mg/dL). Predict death UNLESS full concordant recovery is present across ALL other systems (HE grade 0-1, INR < 1.5, lactate < 2.0, no vasopressors, no ventilation, no infections). If bilirubin >15 AND any other system shows discordance, predict death.
- PERSISTENT GRADE 4 HE (duration-based): APAP recovery clears HE within 2-3 days. Grade 4 HE persisting at Day 4+ in APAP (or Day 5+ in non-APAP) = predict death from cerebral edema/herniation (28% of ALF deaths) UNLESS ALL of these conditions are met: liver function FULLY normalized (INR < 1.5, bilirubin < 5 mg/dL, lactate < 2.0 mmol/L, no active infections, ALT declining) AND PaO2/FiO2 >= 2.0 (no severe ARDS -- severe ARDS with grade 4 HE suggests neurogenic pulmonary edema from cerebral edema). If grade 4 HE + PaO2/FiO2 < 2.0 are both present, predict death even if liver function is normalized -- this combination indicates likely cerebral edema with neurogenic pulmonary edema. Rising lactate strengthens this but is NOT required -- persistent grade 4 HE at Day 4+ with ANY other concerning feature (elevated lactate, bilirubin > 5, infection, elevated INR, severe ARDS) is sufficient. ALFSG-PI treats grade 3 and 4 identically but grade 4 has much higher mortality risk.
- AMMONIA CONTEXT (Day 5+ ONLY): At Day 5+ in APAP (or Day 6+ in non-APAP), when persistent grade 3-4 HE coexists with NORMAL ammonia (<50 umol/L) AND there is an alternative explanation (uremia, sedation), the coma is likely NON-hepatic. Do NOT apply the persistent HE death override. NOTE ON STALE AMMONIA: If ammonia was normal (<50 umol/L) at an earlier time point AND liver function has since recovered or normalized (INR < 1.5), ammonia is almost certainly still normal or lower because the recovered liver clears ammonia efficiently. Treat stale normal ammonia with recovered liver as CONFIRMED normal ammonia. Before Day 5, normal ammonia does NOT rule out established cerebral edema.
- CVVH CREATININE: Low creatinine during active CVVH is NOT evidence of renal recovery (CRRT clears creatinine).
- NEAR-KCC PHENOTYPE WITHOUT TRAJECTORY (day 1-2): When only 1-2 days of data are available AND the patient presents with deep HE (grade 3+) + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL), this is a near-KCC phenotype that the ALFSG-PI fundamentally underestimates (it excludes creatinine and ventilation). Without demonstrated recovery trajectory, predict death when this severity pattern is present regardless of ALFSG-PI.
- DEMONSTRATED RECOVERY OVERRIDES INITIAL PROGNOSIS (Day 5+, NEAR-CONCLUSIVE): When a patient at Day 5+ shows clear hepatic recovery (INR < 1.5, ALT >80% down from peak, bilirubin declining), the liver IS regenerating. This is NEAR-CONCLUSIVE evidence of hepatic recovery that OVERRIDES the initial ALFSG-PI score and etiology-based prognosis. The observed multi-day trajectory is a STRONGER predictor than the initial prognostic snapshot. When demonstrated recovery criteria are met, predict SURVIVAL unless there is active clinical deterioration (rising lactate, worsening creatinine, new infections, hemodynamic collapse). The burden of proof shifts: you need evidence of ACTIVE DETERIORATION to predict death, not just poor initial scores. This applies to ALL etiologies.
- STALE LAB VALUE CAUTION: Lab values from earlier days (>2 days old) should be interpreted with caution, especially lactate and ammonia. Do NOT let stale values override current improving trends. CONVERSELY: if ammonia was NORMAL at an earlier time AND liver function has since improved, the ammonia is almost certainly still normal or lower (recovered liver clears ammonia). Stale normal ammonia with improved liver = reinforced normal ammonia.
- HEPATOLOGIST AUTHORITY ON LIVER RECOVERY: When the Hepatologist identifies clear concordant liver recovery (INR normalized, ALT declining, bilirubin improving) AND predicts survival, but CC and/or TS predict death based on extrahepatic organ failure -- carefully evaluate whether the liver recovery is genuine. If the liver has demonstrably recovered, the question shifts to: "can modern ICU care manage the remaining organ failures?" In ALF with fully normalized liver, remaining organ failures are often reversible with ICU support. Give additional weight to the Hepatologist's liver-specific trajectory assessment when recovery is clear.

Consider the weighted voting and provide comprehensive reasoning that synthesizes all perspectives. When agents disagree, check for override conditions FIRST:
- Extreme bilirubin >15 mg/dL: predict death UNLESS full concordant recovery across ALL other systems (HE 0-1, INR < 1.5, lactate < 2.0, no vasopressors, no ventilation, no infection).
- Persistent grade 4 HE at Day 4+ in APAP (or Day 5+ in non-APAP): predict death UNLESS liver function fully normalized (INR < 1.5, bilirubin < 5, lactate < 2.0, no infections) AND PaO2/FiO2 >= 2.0 (no severe ARDS). Grade 4 HE + PaO2/FiO2 < 2.0 = predict death even if liver normalized.
- AMMONIA CONTEXT (Day 5+ ONLY): At Day 5+, if grade 3-4 HE has normal ammonia (<50 umol/L) AND an alternative explanation exists, the HE override does NOT apply. Stale normal ammonia with recovered liver = confirmed normal ammonia. Before Day 5, normal ammonia does NOT rule out cerebral edema.
- Near-KCC phenotype without trajectory: predict death.
- Demonstrated recovery (Day 5+, NEAR-CONCLUSIVE) with INR < 1.5, ALT >80% down, bilirubin declining: predict SURVIVAL unless active deterioration. This OVERRIDES initial ALFSG-PI and etiology prognosis.
- Ammonia context: if grade 3-4 HE has normal ammonia (<50), the HE override does NOT apply.
- If Hepatologist identifies clear liver recovery and predicts survival, give additional weight to their liver-specific assessment.
If an override condition is met (accounting for the context-dependent exceptions above), predict death regardless of the majority vote. If concordant multi-system recovery is present WITHOUT override conditions, favor survival."""

    prompt = f"""{system_prompt}

Hepatologist Decision (33.33% weight):
Decision: {hepatologist.decision if hepatologist else "N/A"}
Reasoning: {hepatologist.reasoning if hepatologist else "N/A"}

Critical Care Physician Decision (33.33% weight):
Decision: {critical_care.decision if critical_care else "N/A"}
Reasoning: {critical_care.reasoning if critical_care else "N/A"}

Transplant Surgeon Decision (33.33% weight):
Decision: {transplant_surgeon.decision if transplant_surgeon else "N/A"}
Reasoning: {transplant_surgeon.reasoning if transplant_surgeon else "N/A"}

Weighted Analysis:
- Critical Care: {weights['critical_care']*100:.2f}% weight → {critical_care.decision if critical_care else "N/A"}
- Transplant Surgeon: {weights['transplant_surgeon']*100:.2f}% weight → {transplant_surgeon.decision if transplant_surgeon else "N/A"}
- Hepatologist: {weights['hepatologist']*100:.2f}% weight → {hepatologist.decision if hepatologist else "N/A"}
- Weighted Score: {yes_votes:.2f} (threshold: 0.50)
- Weighted Decision: {weighted_decision}

Provide your final synthesis and prediction."""

    client, deployment_name, client_type = get_azure_openai_client()
    logger.info(f"Calling LLM for Final Synthesis with deployment name: {deployment_name}")
    # Use JSON mode for structured output
    response = call_llm(client, client_type, deployment_name, system_prompt, prompt, json_mode=True, json_schema_model=FinalPrediction)
    
    # Check if response is already a parsed Pydantic model (Anthropic native structured outputs)
    if isinstance(response, FinalPrediction):
        prediction = response
    else:
        # Response is a string, need to parse it
        response_text = response
        if not response_text or not response_text.strip():
            logger.error(f"Empty response from LLM. Client type: {client_type}")
            raise ValueError("Empty response from LLM")
        
        response_text = response_text.strip()
        
        # Try to find JSON object in response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_part = response_text[json_start:json_end]
            json_part = clean_json_string(json_part)
            try:
                response_json = json.loads(json_part)
                # Handle case where LLM returns "decision" instead of "prediction" (for FinalPrediction)
                if "decision" in response_json and "prediction" not in response_json:
                    logger.warning("LLM returned 'decision' instead of 'prediction', converting...")
                    response_json["prediction"] = response_json.pop("decision")
                # Validate required fields
                required_fields = ['prediction', 'confidence', 'reasoning']
                if all(field in response_json for field in required_fields):
                    prediction = FinalPrediction(**response_json)
                else:
                    raise ValueError(f"Missing required fields: {required_fields}")
            except Exception as e:
                logger.warning(f"JSON parsing failed for Final Synthesis: {e}, using fallback")
                # Fallback: use weighted decision
                prediction = FinalPrediction(
                    prediction=weighted_decision,
                    confidence=confidence,
                    reasoning=f"Weighted analysis: {yes_votes:.2f} weighted score. JSON parse error: {str(e)}"
                )
        else:
            logger.warning(f"No JSON object found in response, using fallback")
            # Fallback
            prediction = FinalPrediction(
                prediction=weighted_decision,
                confidence=confidence,
                reasoning=f"Weighted analysis: {yes_votes:.2f} weighted score. No JSON found in response."
            )
        
        # Override with calculated values
        prediction.prediction = weighted_decision
        prediction.confidence = confidence
        
        state['final_prediction'] = prediction
        logger.info(f"Final prediction: {prediction.prediction} (confidence: {prediction.confidence:.2f})")
        
    return state

def create_multi_agent_graph():
    """Create the LangGraph workflow for multi-agent system.
    
    Architecture:
    1. All three agents run (can be parallel in actual execution)
    2. Final synthesis waits for all agents to complete
    3. Outputs final prediction
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("hepatologist", hepatologist_agent)
    workflow.add_node("critical_care", critical_care_agent)
    workflow.add_node("transplant_surgeon", transplant_surgeon_agent)
    workflow.add_node("final_synthesis", final_synthesis)
    
    # Sequential execution: run all agents, then synthesis
    # In practice, agents can run in parallel via async/threading
    workflow.set_entry_point("hepatologist")
    workflow.add_edge("hepatologist", "critical_care")
    workflow.add_edge("critical_care", "transplant_surgeon")
    workflow.add_edge("transplant_surgeon", "final_synthesis")
    workflow.add_edge("final_synthesis", END)
    
    return workflow.compile()

def process_patient_day(row: pd.Series, graph) -> dict:
    """Process a single patient-day through the multi-agent system.
    
    Returns a dictionary with:
    - final_prediction: FinalPrediction object
    - hepatologist_output: AgentDecision object
    - critical_care_output: AgentDecision object
    - transplant_surgeon_output: AgentDecision object
    """
    state = {
        "subject_id": int(row['subject_id']),
        "day": int(row['day']),
        "vignette": row['patient_day_vignette'] if pd.notna(row.get('patient_day_vignette')) else "",
        "hepatologist_output": None,
        "critical_care_output": None,
        "transplant_surgeon_output": None,
        "final_prediction": None
    }
    
    # Run the graph
    final_state = graph.invoke(state)
    
    return {
        'final_prediction': final_state['final_prediction'],
        'hepatologist_output': final_state['hepatologist_output'],
        'critical_care_output': final_state['critical_care_output'],
        'transplant_surgeon_output': final_state['transplant_surgeon_output']
    }

def main():
    """Main function to run the multi-agent system on clinical vignettes."""
    parser = argparse.ArgumentParser(description='Multi-Agent System for Clinical Vignette Predictions')
    parser.add_argument('--num_patient', type=int, default=None,
                        help='Number of patients to process (default: all patients)')
    parser.add_argument('--day', type=int, default=None,
                        help='Specific day to process (default: maximum day for each patient)')
    parser.add_argument('--patient_id', type=int, nargs='+', default=None,
                        help='Specific patient ID(s) to process (default: all patients). Can specify multiple IDs separated by spaces.')
    parser.add_argument('--deployment', type=str, default='gpt-5',
                        help='Deployment/model name to use (default: gpt-5). Options: gpt-5, gpt-4.1-mini, gpt-5-mini, claude-opus-4-1, claude-sonnet-4-5')
    
    args = parser.parse_args()
    
    start_time = time.time()
    
    # Set deployment name globally via environment variable so all agents use it
    os.environ["DEPLOYMENT_NAME"] = args.deployment
    
    logger.info("Initializing Multi-Agent System")
    logger.info(f"Using deployment: {args.deployment}")
    
    # Load clinical vignettes
    input_file = 'clinical_vignettes.xlsx'
    logger.info(f"Loading {input_file}")
    df = pd.read_excel(input_file)
    logger.info(f"Loaded {len(df)} patient-day combinations")
    
    # Filter by day: if day is None, use maximum day for each patient
    # If day < 1, use day 1 for each patient
    # If day > maximum day for a patient, use maximum day for that patient
    max_day_per_patient = df.groupby('subject_id')['day'].max().reset_index()
    max_day_per_patient.columns = ['subject_id', 'max_day']
    df = df.merge(max_day_per_patient, on='subject_id')
    
    if args.day is None:
        logger.info("No specific day provided, filtering to maximum day for each patient")
        df = df[df['day'] == df['max_day']].drop(columns=['max_day'])
        logger.info(f"Filtered to maximum day per patient: {len(df)} patient-day combinations")
    else:
        # Determine target day for each patient based on specified day
        # If specified_day < 1, use day 1; if specified_day > max_day, use max_day; otherwise use specified_day
        # Formula: target_day = max(1, min(specified_day, max_day))
        logger.info(f"Specified day: {args.day}")
        
        # For each patient, determine the actual target day
        df['target_day'] = df.apply(
            lambda row: max(1, min(args.day, row['max_day'])),
            axis=1
        )
        
        # Filter to keep only rows where day matches the target day
        df = df[df['day'] == df['target_day']].drop(columns=['max_day', 'target_day'])
        logger.info(f"Filtered to target day per patient (specified: {args.day}, clamped to [1, max_day] per patient): {len(df)} patient-day combinations")
    
    # Filter by specific patient IDs if specified
    if args.patient_id is not None:
        df = df[df['subject_id'].isin(args.patient_id)]
        logger.info(f"Filtered to patient IDs {args.patient_id}: {len(df)} patient-day combinations")
    
    # Filter by number of patients if specified
    if args.num_patient is not None:
        unique_patients = df['subject_id'].unique()[:args.num_patient]
        df = df[df['subject_id'].isin(unique_patients)]
        logger.info(f"Filtered to {args.num_patient} patients: {len(df)} patient-day combinations")
    
    if len(df) == 0:
        logger.warning("No patient-day combinations to process after filtering")
        return
    
    # Create the graph
    logger.info("Creating LangGraph workflow...")
    graph = create_multi_agent_graph()
    
    # Process all filtered patient-day combinations
    logger.info(f"Processing {len(df)} patient-day combinations...")
    results = []
    
    for idx, row in df.iterrows():
        logger.info(f"\nProcessing Subject {int(row['subject_id'])}, Day {int(row['day'])}")
        try:
            outputs = process_patient_day(row, graph)
            final_pred = outputs['final_prediction']
            hepatologist = outputs['hepatologist_output']
            critical_care = outputs['critical_care_output']
            transplant_surgeon = outputs['transplant_surgeon_output']
            
            actual_survival_val = row.get('Spont_Survival21', None)
            actual_survival_text = "Yes" if actual_survival_val == 1 else ("No" if actual_survival_val == 0 else None)
            
            results.append({
                'subject_id': int(row['subject_id']),
                'day': int(row['day']),
                'patient_day_vignette': row.get('patient_day_vignette', ''),
                'final_prediction': final_pred.prediction if final_pred else None,
                'final_confidence': final_pred.confidence if final_pred else None,
                'final_reasoning': final_pred.reasoning if final_pred else None,
                'hepatologist_decision': hepatologist.decision if hepatologist else None,
                'hepatologist_confidence': hepatologist.confidence if hepatologist else None,
                'hepatologist_reasoning': hepatologist.reasoning if hepatologist else None,
                'critical_care_decision': critical_care.decision if critical_care else None,
                'critical_care_confidence': critical_care.confidence if critical_care else None,
                'critical_care_reasoning': critical_care.reasoning if critical_care else None,
                'transplant_surgeon_decision': transplant_surgeon.decision if transplant_surgeon else None,
                'transplant_surgeon_confidence': transplant_surgeon.confidence if transplant_surgeon else None,
                'transplant_surgeon_reasoning': transplant_surgeon.reasoning if transplant_surgeon else None,
                'actual_survival': actual_survival_val,
                'actual_survival_text': actual_survival_text,
                'Final_Correct': (final_pred.prediction == actual_survival_text) if (final_pred and actual_survival_text) else None,
                'hepatologist_correct': (hepatologist.decision == actual_survival_text) if (hepatologist and actual_survival_text) else None,
                'critical_care_correct': (critical_care.decision == actual_survival_text) if (critical_care and actual_survival_text) else None,
                'transplant_surgeon_correct': (transplant_surgeon.decision == actual_survival_text) if (transplant_surgeon and actual_survival_text) else None
            })
            logger.info(f"Final Prediction: {final_pred.prediction if final_pred else 'N/A'} (confidence: {final_pred.confidence if final_pred else 0.0:.2f})")
        except Exception as e:
            logger.error(f"Error processing row {idx}: {e}")
            actual_survival_val = row.get('Spont_Survival21', None)
            actual_survival_text = "Yes" if actual_survival_val == 1 else ("No" if actual_survival_val == 0 else None)
            
            results.append({
                'subject_id': int(row['subject_id']),
                'day': int(row['day']),
                'patient_day_vignette': row.get('patient_day_vignette', ''),
                'final_prediction': 'Error',
                'final_confidence': 0.0,
                'final_reasoning': str(e),
                'hepatologist_decision': None,
                'hepatologist_confidence': None,
                'hepatologist_reasoning': None,
                'critical_care_decision': None,
                'critical_care_confidence': None,
                'critical_care_reasoning': None,
                'transplant_surgeon_decision': None,
                'transplant_surgeon_confidence': None,
                'transplant_surgeon_reasoning': None,
                'actual_survival': actual_survival_val,
                'actual_survival_text': actual_survival_text,
                'Final_Correct': None,
                'hepatologist_correct': None,
                'critical_care_correct': None,
                'transplant_surgeon_correct': None
            })
    
    # Always save results to Excel file
    results_df = pd.DataFrame(results)
    
    # Calculate accuracy metrics
    # Filter out rows where actual_survival_text is None (no ground truth available)
    valid_df = results_df[results_df['actual_survival_text'].notna()].copy()
    
    if len(valid_df) > 0:
        # Calculate accuracy for each agent and final prediction
        final_accuracy = valid_df['Final_Correct'].sum() / len(valid_df) if 'Final_Correct' in valid_df.columns else 0.0
        hepatologist_accuracy = valid_df['hepatologist_correct'].sum() / len(valid_df) if 'hepatologist_correct' in valid_df.columns else 0.0
        critical_care_accuracy = valid_df['critical_care_correct'].sum() / len(valid_df) if 'critical_care_correct' in valid_df.columns else 0.0
        transplant_surgeon_accuracy = valid_df['transplant_surgeon_correct'].sum() / len(valid_df) if 'transplant_surgeon_correct' in valid_df.columns else 0.0
        
        logger.info(f"\nAccuracy Metrics (based on {len(valid_df)} predictions with ground truth):")
        logger.info(f"  Final Prediction Accuracy: {final_accuracy:.4f} ({final_accuracy*100:.2f}%)")
        logger.info(f"  Hepatologist Accuracy: {hepatologist_accuracy:.4f} ({hepatologist_accuracy*100:.2f}%)")
        logger.info(f"  Critical Care Physician Accuracy: {critical_care_accuracy:.4f} ({critical_care_accuracy*100:.2f}%)")
        logger.info(f"  Transplant Surgeon Accuracy: {transplant_surgeon_accuracy:.4f} ({transplant_surgeon_accuracy*100:.2f}%)")
    else:
        logger.warning("No valid ground truth data available for accuracy calculation")
    
    output_file = f'agent_predictions_{args.deployment}.xlsx'
    # Clean illegal characters from string columns before Excel export
    # openpyxl rejects certain Unicode control characters
    for col in results_df.select_dtypes(include=['object']).columns:
        results_df[col] = results_df[col].apply(
            lambda x: re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', str(x)) if isinstance(x, str) else x
        )
    results_df.to_excel(output_file, index=False, engine='openpyxl')
    logger.info(f"\nSaved predictions to {output_file}")
    logger.info(f"\nResults summary:")
    logger.info(f"Total predictions: {len(results_df)}")
    logger.info(f"Results saved to {output_file}")
    
    elapsed_time = time.time() - start_time
    logger.info(f"Total execution time: {elapsed_time:.2f} seconds")
    
    logger.info(f"\n{results_df.to_string()}")

if __name__ == '__main__':
    main()

