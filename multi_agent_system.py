import os
import json
import logging
import argparse
import pandas as pd
import time
from datetime import datetime
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
   - **EXTREME BILIRUBIN OVERRIDE (CONTEXT-DEPENDENT):** When bilirubin rises to >15 mg/dL in APAP ALF (approaching the non-APAP KCC threshold of 17 mg/dL), this is NOT normal lagging -- it typically indicates catastrophic hepatic excretory failure. Typical APAP bilirubin lag reaches ~8-12 mg/dL. HOWEVER, this override is context-dependent: if bilirubin is 15-17 mg/dL AND full concordant recovery is present across ALL other systems (HE resolved to grade 0-1, INR < 1.5, lactate <=2.0 mmol/L, no vasopressors, no mechanical ventilation, no active infections), this may represent a variant of APAP bilirubin lag rather than catastrophic failure -- in this specific combination, do NOT automatically predict death. If bilirubin >15 mg/dL AND any other system shows discordance (HE grade 2+, INR >= 1.5, lactate >2.0, vasopressors, ventilation, infection), predict death. BILIRUBIN LAG IN APAP: When Priority 1C bilirubin lag exception criteria are met (peak INR 2-5, ALT >80% down, HE 0-1, no vent, no pressors, no infection, creatinine OK, lactate <=2), rising bilirubin even >15 is excretory lag, NOT catastrophic failure -- predict SURVIVAL.
   - **PERSISTENT GRADE 4 HE (DURATION-BASED):** APAP recovery typically shows rapid neurological clearing within 2-3 days. Persistent grade 4 HE at Day 4+ in APAP (or Day 5+ in non-APAP) is a critical death signal because 28% of ALF deaths are neurologic (cerebral edema/herniation, Karvellas 2023). The ALFSG-PI treats grades 3 and 4 identically (both "deep"), but grade 4 carries substantially higher mortality risk. Predict death when grade 4 HE persists at Day 4+ UNLESS ALL of these conditions are met: liver function FULLY normalized (INR < 1.5, bilirubin < 5 mg/dL, lactate < 2.0 mmol/L, no active infections, ALT declining) AND PaO2/FiO2 >= 2.0 (no severe ARDS). These exception conditions are EXHAUSTIVE: if ALL are met, the exception applies REGARDLESS of vasopressors, ventilation, AKI, or elevated WBC (leukocytosis without documented infection is NOT "infection"). If grade 4 HE + PaO2/FiO2 < 2.0, predict death even if liver normalized. The ONLY features that strengthen this override are: lactate >2 mmol/L, bilirubin >5 mg/dL, documented infection, INR >1.5, PaO2/FiO2 <2.0. No other features (vasopressors, ventilation, AKI, WBC) apply. NOTE: This override is SUPERSEDED by demonstrated recovery at Day 5+ (see Step 8, Priority 1) -- but NOT at Day 4. At Day 4, this override is the PRIMARY evaluation because Priority 1/1B/1C require Day 5+. Even with INR 1.0, persistent grade 4 HE for 4 days + PaO2/FiO2 < 2.0 = DEATH from neurologic cause, not hepatic. NOTE: Grade 3 HE is NOT grade 4 and does NOT trigger this override.
   - **AMMONIA CONTEXT FOR HE ASSESSMENT (Day 5+ ONLY, NOT Day 4):** Hepatic encephalopathy is driven by hyperammonemia. At Day 5+ in APAP (or Day 6+ in non-APAP), when persistent grade 3-4 HE coexists with NORMAL ammonia (<50 umol/L) AND there is an alternative explanation for the altered consciousness (elevated creatinine suggesting uremic encephalopathy, heavy sedation for mechanical ventilation, ICU delirium), the coma is likely NON-hepatic in origin. In this specific context, the deep HE does NOT carry the same cerebral edema/herniation risk and should NOT trigger the persistent HE death override. STALE AMMONIA RULE (BINDING): If ammonia was normal (<50 umol/L) at ANY earlier time point AND liver function has since recovered (INR < 1.5), ammonia is CONFIRMED normal. This is a PHYSIOLOGICAL CERTAINTY. IMPORTANT: Do NOT apply this ammonia context rule before Day 5 -- at Day 3-4, cerebral edema from earlier hyperammonemia can still be progressing even if ammonia has now normalized. At Day 4 specifically, do NOT use low ammonia to reclassify grade 4 HE as non-hepatic.
   - **CVVH AND CREATININE:** When CVVH/CRRT is active, creatinine may be artificially low because CRRT clears creatinine. Do NOT count low creatinine during active CVVH as evidence of renal recovery. The need for continuous CVVH itself is a marker of persistent organ dysfunction.
   - **EARLY PRESENTATION WITHOUT TRAJECTORY (day 1-2):** When only 1-2 days of data are available, concordant recovery CANNOT be demonstrated because there is no trajectory. Do NOT assume recovery will occur based on ALFSG-PI alone. A high-severity day-1 presentation with deep HE (grade 3+) + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) is a near-KCC phenotype that the ALFSG-PI fundamentally underestimates (it excludes creatinine and ventilation). Without demonstrated recovery, predict death when this severity pattern is present.
   - **EARLY CRITICAL METABOLIC WARNING (Day 2-3 BINDING; Day 1 CONDITIONAL):** At Day 2-3, patients may show PARTIAL improvement (e.g., INR declining, creatinine improving) while retaining critical metabolic derangements that predict death. This check evaluates CURRENT VALUES at the time of assessment, NOT trends. When ANY of the following are present at Day 2-3, predict DEATH regardless of other improvements: (a) ammonia >150 umol/L -- this is BINDING: ammonia >150 carries significant ICH risk (Kumar/Bernal) REGARDLESS of whether it is declining from a higher value. An ammonia of 152 declining from 487 is STILL >150 and STILL carries ICH risk. (b) lactate >4 mmol/L AND not declining from prior days (stagnant or rising), (c) bilirubin actively rising (upward TREND through Days 1-3). DAY 1 EXCEPTION: At Day 1 ONLY, ammonia >150 is NOT binding if ALL of: (a) HE grade 0-1, (b) no mechanical ventilation, (c) no vasopressor support. Rationale: on Day 1, ammonia is often at its presentation peak before NAC and supportive care have had time to reduce it; grade 0-1 HE means the brain is currently tolerating the ammonia load without significant encephalopathy. At Day 2-3, ammonia >150 despite treatment IS binding because treatment has had time to work. If Day 1 AND (HE grade 2+ OR ventilation OR vasopressors), ammonia >150 IS still binding. This is BINDING and FINAL at Day 2-3: do NOT override this warning with partial improvement in INR or creatinine. This is distinct from Day 5+ demonstrated recovery where multi-day concordant improvement IS conclusive.
   - **DEMONSTRATED RECOVERY OVERRIDES INITIAL PROGNOSIS (Day 5+ ONLY, NOT Day 4, NEAR-CONCLUSIVE):** When a patient at Day 5+ shows clear hepatic recovery trajectory -- INR normalized to <1.5 (from initially elevated), ALT declined >80% from peak, AND bilirubin is declining (or already near-normal at <3 mg/dL) -- the liver IS regenerating. STRICT BILIRUBIN: "declining" means the MOST RECENT trend is downward. If the vignette shows bilirubin as "Increasing" (even slightly), it is NOT declining -- even if below the overall peak. A bilirubin rebound (was declining then reversed upward) is NOT declining. At Day 4, do NOT apply this rule -- use persistent grade 4 HE override instead. This is NEAR-CONCLUSIVE evidence of hepatic recovery that OVERRIDES the initial ALFSG-PI score and etiology-based prognosis, regardless of how poor they were. When demonstrated recovery criteria are met, predict SURVIVAL unless there is active clinical deterioration (rising lactate, worsening creatinine, new infections, hemodynamic collapse). The burden of proof shifts: you need evidence of ACTIVE DETERIORATION to predict death, not just poor initial scores.
   - **PARTIAL RECOVERY (Day 5+):** When INR has improved >60% from peak AND the peak INR was >5.0 (indicating severe initial coagulopathy), combined with ALT declined >80% from peak AND at least one of: lactate normalized (<2 mmol/L), HE resolved to grade 0-1, or creatinine improving -- the liver IS regenerating even though INR has not yet reached <1.5. This "partial recovery" is a strong survival signal because: (1) the magnitude of INR improvement from extreme levels demonstrates active hepatic protein synthesis, (2) ALT decline confirms the necrotic phase has ended, and (3) normalization of other markers confirms the systemic inflammatory response is resolving. Predict SURVIVAL with partial recovery unless ACTIVE DETERIORATION (rising lactate AND worsening creatinine AND new infections -- not isolated single-organ worsening).
   - **STALE LAB VALUE CAUTION:** Some lab values may be from earlier days (indicated by "from day X"). Values more than 2 days old should be interpreted with significant caution, particularly lactate and ammonia which change rapidly. In a patient showing clear recovery trajectory at day 5+, a stale elevated lactate from early presentation should NOT override current improving trends. CONVERSELY: if ammonia was NORMAL at an earlier time AND liver function has since improved, the ammonia is almost certainly still normal or lower (recovered liver clears ammonia). Stale normal ammonia with improved liver = reinforced normal ammonia.
   - **APAP-SPECIFIC LACTATE CONTEXT:** In APAP ALF, extreme lactate elevation (even >15-20 mmol/L) may represent Type B lactic acidosis from NAPQI-induced mitochondrial dysfunction (NAD+ depletion), NOT circulatory failure. Key distinguishing features of mitochondrial lactate: (a) hemodynamically STABLE -- no vasopressors or vasopressors not escalating, (b) pH improving or near-normal despite extreme lactate (metabolic compensation), (c) no clinical signs of shock. When extreme lactate coexists with hemodynamic stability and improving pH in APAP, it should be interpreted cautiously -- do NOT automatically equate with tissue hypoperfusion or impending death. The lactate will gradually clear as mitochondrial function recovers. This is specific to APAP (direct hepatocyte mitochondrial toxin) and does NOT apply to other etiologies.
   - **ISOLATED CREATININE WORSENING CONTEXT:** In APAP ALF, acute kidney injury (AKI) often follows a delayed trajectory -- creatinine may continue to WORSEN for 3-5 days after liver recovery begins due to acute tubular necrosis (ATN) from the initial hemodynamic insult. Isolated creatinine worsening (without rising lactate, without hemodynamic collapse, without new infections) is a WEAKER signal of deterioration than multi-organ worsening. When the liver has recovered (or partially recovered) and only creatinine is worsening, this is likely ATN progression that will eventually recover with continued renal support. Do NOT classify isolated creatinine worsening as "active deterioration" when all other markers are stable or improving.

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

**Step 8: Check for Override Conditions (EVALUATE IN PRIORITY ORDER)**
- **MANDATORY PRE-CHECK A -- UREMIC ENCEPHALOPATHY (BINDING, CHECK FIRST):** Before evaluating ANY override, check: Is grade 3-4 HE present AND ammonia normal (<50 umol/L) AND creatinine >5 mg/dL? If ALL THREE are true, the encephalopathy is UREMIC, not hepatic. This determination is BINDING and FINAL -- you MUST NOT add extra conditions (CRRT status, ventilation status, neurologic improvement, hepatic normalization are ALL IRRELEVANT to this determination). The physiology is clear: hepatic encephalopathy REQUIRES hyperammonemia; normal ammonia + severe uremia = uremic coma. Uremic encephalopathy does NOT carry cerebral edema/herniation risk and is REVERSIBLE with renal replacement. If HE is uremic, the persistent grade 4 HE death override is NULLIFIED for this patient. Proceed to assess liver trajectory and other organs without the HE penalty. Record: "HE determined to be uremic (ammonia [value], creatinine [value]) -- HE death override nullified."
- **MANDATORY PRE-CHECK B -- EARLY CRITICAL METABOLIC WARNING (Day 2-3 BINDING; Day 1 CONDITIONAL):** At Day 2-3, check CURRENT VALUES (not trends): ammonia >150 umol/L AND/OR lactate >4 not declining AND/OR bilirubin actively rising = predict DEATH. This is BINDING and FINAL. CRITICAL: ammonia >150 means the CURRENT reading is above 150, regardless of whether it is declining from a higher value. Ammonia 152 (down from 487) is STILL >150 and STILL triggers this check. Do NOT rationalize that declining ammonia is "improving" when it remains above the lethal threshold. DAY 1 EXCEPTION: At Day 1 ONLY, ammonia >150 is NOT binding if ALL of: (a) HE grade 0-1, (b) no mechanical ventilation, (c) no vasopressor support. Rationale: on Day 1, ammonia is at its presentation peak before NAC and supportive care have had time to reduce it; grade 0-1 HE means the brain is currently tolerating the ammonia load. If Day 1 AND (HE grade 2+ OR ventilation OR vasopressors), ammonia >150 IS still binding. Record: "Pre-Check B triggered: [values]. Predict death." OR "Day 1 exception applied: ammonia [value] but HE grade [X], no vent, no pressors -- monitoring."
- **MANDATORY PRE-CHECK C -- MECHANICAL VENTILATION AT DAY 1-3 (BINDING):** At Day 1-3, if the patient is receiving mechanical ventilation, this is a CRITICAL independent mortality predictor that ALFSG-PI does NOT capture. Predict DEATH. Rationale: Mechanical ventilation at Day 1-3 indicates disease severity (profound neurological compromise, aspiration risk, respiratory failure) beyond what laboratory trajectories can assess within 1-3 days. Even if hepatic markers are improving (INR declining, ALT down >70%, bilirubin decreasing), ventilator dependence at Day 1-3 represents a severity phenotype incompatible with spontaneous recovery. A favorable ALFSG-PI (even >80%) is UNRELIABLE when the patient requires ventilation because ALFSG-PI does not model ventilation status. Do NOT let improving liver labs override mechanical ventilation at Day 1-3. Record: "Pre-Check C triggered: mechanical ventilation at Day [X]. Predict death."
- **PRIORITY 1 -- DEMONSTRATED RECOVERY (Day 5+ ONLY, NOT Day 4):** If INR < 1.5 (from elevated), ALT >80% down from peak, AND bilirubin declining (or near-normal <3 mg/dL), the liver IS regenerating. STRICT BILIRUBIN CHECK (BINDING): "bilirubin declining" means the MOST RECENT trend is downward. If the vignette reports bilirubin trend as "Increasing" (e.g., 15.5->15.8 or 5.5->7.2->7.8), bilirubin is NOT declining -- even if the current value is below the overall peak from earlier days. A bilirubin REBOUND (was declining then reverses upward) is NOT declining. If bilirubin is not declining by this strict definition, Priority 1 is NOT met -- check Priority 1B and 1C next (they have DIFFERENT criteria and do NOT require bilirubin declining). Predict SURVIVAL unless ACTIVE DETERIORATION (rising lactate AND/OR new infections AND/OR hemodynamic collapse). Isolated creatinine worsening is NOT active deterioration (ATN lag). If demonstrated recovery met without active deterioration, predict survival and SKIP death overrides. ONE EXCEPTION: grade 4 HE with PaO2/FiO2 < 2.0 AND HE is NOT uremic. IMPORTANT: This requires Day 5+. At Day 4, do NOT apply Priority 1/1B/1C -- evaluate persistent grade 4 HE override and other death overrides directly.
- **PRIORITY 1B -- PARTIAL RECOVERY (Day 5+, NO BILIRUBIN REQUIREMENT, BINDING):** If INR improved >60% from peak >5.0, combined with ALT >80% down AND at least one of: lactate <2, HE grade 0-1, or creatinine improving -- liver IS regenerating. CALCULATING INR IMPROVEMENT: percentage = (peak - current) / peak. Example: peak 12.0 to current 2.46 = (12.0 - 2.46)/12.0 = 79.5% -- this MEETS >60%. There is NO requirement for the resulting INR to be below any specific value. This does NOT require bilirubin to be declining (unlike Priority 1). Rising bilirubin does NOT negate Priority 1B. Predict SURVIVAL unless ALL THREE present: rising lactate AND worsening creatinine AND new infections. Vasopressors and mechanical ventilation alone do NOT negate Priority 1B when lactate is normal (<2). Isolated creatinine worsening (even severe, e.g., 6.3 mg/dL) is ATN lag in APAP, NOT multi-organ deterioration. If Priority 1B criteria are met and ALL THREE negation criteria are NOT present, you MUST predict SURVIVAL.
- **PRIORITY 1C -- MODERATE-INR HEPATIC RECOVERY (Day 5+, BINDING):** Check these EXACT criteria: (a) peak INR was 2.0-5.0, (b) ALT declined >80% from peak, (c) lactate normalized <=2 mmol/L OR HE resolved to grade 0-1, (d) bilirubin is lower than the patient's own peak value (declining from THEIR peak, regardless of absolute level). If ALL four criteria are met, the liver IS regenerating despite moderate initial coagulopathy. Predict SURVIVAL unless multi-organ active deterioration. Note: bilirubin 14.2 declining from a peak of 19.5 DOES satisfy "declining from peak" even though the absolute value is still elevated -- the trend matters, not the level. BILIRUBIN LAG EXCEPTION (APAP ONLY): If criteria (a), (b), and (c) are met but bilirubin is STILL RISING (has not peaked yet), Priority 1C IS STILL MET if ALL of: HE grade 0-1, no mechanical ventilation, no vasopressor support, no documented infection, creatinine stable or improving, AND lactate <=2.0 or declining to <=2.0. STALE LACTATE PROVISION: If the most recent available lactate was <=2.0 (even if from a prior day) AND there has been no subsequent metabolic deterioration (no vasopressors added, no new infection, creatinine stable/improving, no acidosis), the stale lactate reading satisfies the <=2.0 requirement. Rationale: lactate reflects hepatic and systemic metabolic function; if it was normal and no deterioration occurred since, it remains physiologically valid. In APAP hyperacute ALF, bilirubin excretory lag commonly continues rising for days after synthetic function (INR) has recovered. When ALL other organ systems confirm recovery (no organ support, resolved HE, normal/improving renal function, low lactate), rising bilirubin alone is bilirubin lag, NOT failed regeneration.
- **PRIORITY 2 -- Only if NO recovery criteria met AND HE is not uremic (per Pre-Check A):**
- EXTREME BILIRUBIN (BINDING): If bilirubin >15 mg/dL in APAP AND bilirubin is NOT declining, predict DEATH unless ALL of: HE grade 0-1, lactate <=2.0, no mechanical ventilation, no vasopressors, no infection. This exception is EXHAUSTIVE. If ANY discordance exists (HE grade 2+, OR lactate >2.0, OR mechanical ventilation, OR vasopressors, OR infection), predict DEATH. Near-normal INR and declining ALT do NOT override extreme bilirubin with discordance -- the liver's synthetic function can recover while its excretory function fails catastrophically.
- PERSISTENT GRADE 4 HE (duration-based): If grade 4 HE persists at Day 4+ AND HE is NOT uremic (see Pre-Check A), predict death UNLESS ALL exception conditions met (INR < 1.5, bilirubin < 5, lactate < 2.0, no infections, ALT declining, PaO2/FiO2 >= 2.0). Exception conditions are EXHAUSTIVE -- vasopressors/ventilation/AKI/WBC are NOT disqualifying. Grade 3 HE does NOT trigger this override. DAY 4 CRITICAL: At Day 4, this override is the PRIMARY evaluation criterion because Priority 1/1B/1C are NOT available (Day 5+ only). Even if liver labs are fully normalized (INR 1.0), persistent grade 4 HE for 4 consecutive days + PaO2/FiO2 < 2.0 = predict DEATH. The risk is NEUROLOGIC (cerebral edema/herniation from prolonged grade 4 coma + respiratory failure), not hepatic. 28% of ALF deaths are neurologic. Do NOT use low ammonia to dismiss grade 4 HE at Day 4 -- the ammonia context rule is Day 5+ ONLY.
- AMMONIA CONTEXT (Day 5+ ONLY, NOT Day 4): If grade 3-4 HE + NORMAL ammonia (<50) + alternative explanation (uremia, sedation) at Day 5+, HE override does NOT apply. Stale normal ammonia + recovered liver (INR < 1.5) = CONFIRMED normal (physiological certainty). At Day 4, do NOT use low ammonia to reclassify grade 4 HE as non-hepatic -- cerebral edema from earlier hyperammonemia can still be progressing.
- CVVH CREATININE: If CVVH is active, do NOT count low creatinine as recovery.
- APAP LACTATE CONTEXT: In APAP ALF, extreme lactate (even >15-20 mmol/L) with hemodynamic stability (no vasopressors or stable, pH improving/near-normal) represents Type B lactic acidosis from mitochondrial dysfunction. Key distinguishing feature: OSCILLATING lactate (going up AND down) without hemodynamic deterioration = mitochondrial origin. Steadily RISING lactate with vasopressor escalation = true tissue hypoperfusion. Do NOT predict death from mitochondrial lactate.

**Step 9: Synthesize and Make Final Prediction**
- FIRST: Check Pre-Check C result. If Day 1-3 AND patient is on mechanical ventilation: predict DEATH immediately. This is BINDING. Mechanical ventilation at Day 1-3 is an independent mortality predictor not captured by ALFSG-PI.
- SECOND: Check Pre-Check B result. If Day 2-3 AND ammonia >150 or lactate >4 not declining or bilirubin rising: predict DEATH immediately. This is BINDING. At Day 1, ammonia >150 is NOT binding if HE grade 0-1 + no vent + no pressors (Day 1 exception). A declining ammonia still >150 is STILL lethal at Day 2-3. DAY 1 EXCEPTION ENFORCEMENT: When the Day 1 exception IS active (ammonia >150 BUT HE 0-1 AND no vent AND no pressors), you MUST NOT use ammonia as the primary basis for predicting death. The exception exists because Day 1 ammonia is at presentation peak before NAC treatment, and HE 0-1 confirms brain tolerance. With favorable etiology (APAP) and ALFSG-PI >85% and no organ support at Day 1, ammonia alone does NOT predict death -- base your prediction on ALFSG-PI, etiology, and clinical stability instead.
- THIRD: Check Pre-Check A result. If HE was determined to be uremic, the HE death override is NULLIFIED. Do NOT let grade 4 HE drive a death prediction when the coma is uremic.
- FOURTH: At Day 4 with persistent grade 4 HE + PaO2/FiO2 < 2.0 (and HE not uremic): predict DEATH. Priority 1/1B/1C are NOT available at Day 4. Do NOT use low ammonia to dismiss grade 4 HE at Day 4.
- If ANY recovery criteria are met (Priority 1, 1B, or 1C including bilirubin lag exception at Day 5+) AND no multi-organ active deterioration: your decision MUST be "Yes." For Priority 1B specifically: negation requires ALL THREE of rising lactate + worsening creatinine + new infections. Vasopressors, ventilation, rising bilirubin, and isolated creatinine worsening do NOT negate Priority 1B. For Priority 1C: if bilirubin is still rising but ALL other systems confirm recovery (HE 0-1, no vent, no pressors, no infection, creatinine OK, lactate <=2), the bilirubin lag exception applies and 1C is met. As a HEPATOLOGIST, liver recovery is YOUR domain of expertise. When the liver is regenerating (INR improving, ALT >80% down, lactate <=2), persistent extrahepatic issues (creatinine, ventilation, pressors) are ICU management problems, not hepatology problems. STRICT BILIRUBIN: If bilirubin trend is "Increasing," Priority 1 specifically is NOT met -- but check Priority 1B and 1C which have DIFFERENT criteria. Priority 1B does NOT require bilirubin declining. Priority 1C has a bilirubin lag exception for APAP when all other systems are favorable.
- COMBINATION SIGNAL: When BOTH moderate-INR recovery (Priority 1C) AND uremic HE (Pre-Check A) are present, this is a STRONG survival signal -- the liver injury is resolving AND the coma is non-hepatic/reversible.
- Grade 3 HE is NOT grade 4 -- does NOT trigger the persistent grade 4 HE death override.
- CRITICAL PEAK INR VERIFICATION: Before claiming ANY recovery criteria are met, verify the peak INR: Priority 1B requires peak INR >5.0. Priority 1C requires peak INR 2.0-5.0. If peak INR is <2.0 (e.g., 1.8), NEITHER Priority 1B NOR 1C can be invoked. In that case, the ONLY recovery pathway is Priority 1 (INR <1.5 + ALT >80% + bilirubin declining). "Bilirubin declining" means the MOST RECENT trend is downward. If the most recent bilirubin trend is even slightly upward (e.g., 15.5->15.8), Priority 1 is NOT met. A patient with peak INR <2.0 AND bilirubin not declining has NO formal recovery criteria available, regardless of how normalized the INR is or how much ALT has declined.
- CRITICAL: When NO Priority 1/1B/1C criteria are formally met (including bilirubin lag exception), you CANNOT predict survival based on informal clinical impression. You MUST evaluate and apply Priority 2 death overrides. If bilirubin >15 AND not declining AND any discordance exists: predict DEATH. Do NOT rationalize that "the liver is recovering" when the formal recovery criteria are not satisfied. Normalized INR + declining ALT do NOT equal "recovery" unless the formal Priority criteria are met.
- EXTREME BILIRUBIN ENFORCEMENT (BINDING, FINAL CHECK): Before outputting your prediction, if bilirubin is >15 mg/dL in APAP AND not declining AND NO formal recovery criteria (Priority 1/1B/1C) are met, verify: are ALL five exception conditions met (HE 0-1, lactate <=2.0, no mechanical ventilation, no vasopressors, no infection)? If ANY SINGLE exception is NOT met (e.g., ventilation IS present, OR HE IS grade 2+, OR lactate is stale/unknown), you MUST predict DEATH. This is NON-NEGOTIABLE.
- When Priority 1 criteria ARE met (INR <1.5, ALT >80% down, bilirubin declining at Day 5+): predict SURVIVAL. The ONLY exception is non-uremic grade 4 HE (NOT grade 3) with PaO2/FiO2 < 2.0. Mechanical ventilation alone, grade 3 HE alone, and severe creatinine/AKI alone are NOT grounds to override Priority 1. These are ICU-manageable complications when the liver is regenerating.
- Only apply death overrides when: (a) Pre-Check B not triggered, AND (b) no recovery criteria are met, AND (c) HE is not uremic, AND (d) the override condition is genuinely present.

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
   - **EXTREME BILIRUBIN OVERRIDE (context-dependent):** Bilirubin >15 mg/dL in APAP ALF is NOT normal lagging (typical lag ~8-12 mg/dL). It typically indicates catastrophic excretory failure. HOWEVER, if bilirubin is 15-17 mg/dL AND full concordant recovery is present across ALL other systems (HE grade 0-1, INR < 1.5, lactate <=2.0, no vasopressors, no ventilation, no infections), this may be a variant of APAP lag -- do NOT automatically predict death. If bilirubin >15 AND any other system shows discordance (HE 2+, lactate >2.0, vent, pressors, infection), predict death. BILIRUBIN LAG: When Priority 1C bilirubin lag exception criteria are met (peak INR 2-5, ALT >80% down, HE 0-1, no vent, no pressors, no infection, creatinine OK, lactate <=2), rising bilirubin even >15 is excretory lag, NOT catastrophic failure.
   - **PERSISTENT GRADE 4 HE (duration-based):** APAP recovery typically clears HE within 2-3 days. Grade 4 HE persisting at Day 4+ in APAP (or Day 5+ in non-APAP) = predict death UNLESS ALL of these conditions are met: liver function FULLY normalized (INR < 1.5, bilirubin < 5 mg/dL, lactate < 2.0 mmol/L, no active infections, ALT declining) AND PaO2/FiO2 >= 2.0. These exception conditions are EXHAUSTIVE: if ALL are met, the exception applies REGARDLESS of vasopressors, ventilation, AKI, or elevated WBC (leukocytosis without documented infection is NOT "infection"). If grade 4 HE + PaO2/FiO2 < 2.0, predict death even if liver normalized. The ONLY features that strengthen this override are: lactate >2 mmol/L, bilirubin >5 mg/dL, documented infection, INR >1.5, PaO2/FiO2 <2.0. No other features apply. NOTE: This override is SUPERSEDED by demonstrated recovery at Day 5+ (see Step 8, Priority 1). NOTE: Grade 3 HE is NOT grade 4 and does NOT trigger this override.
   - **AMMONIA CONTEXT FOR HE ASSESSMENT (Day 5+ ONLY):** Hepatic encephalopathy is driven by hyperammonemia. At Day 5+ in APAP (or Day 6+ in non-APAP), when persistent grade 3-4 HE coexists with NORMAL ammonia (<50 umol/L) AND there is an alternative explanation for the altered consciousness (elevated creatinine suggesting uremic encephalopathy, heavy sedation for mechanical ventilation, ICU delirium), the coma is likely NON-hepatic in origin. In this specific context, the deep HE does NOT carry the same cerebral edema/herniation risk and should NOT trigger the persistent HE death override. STALE AMMONIA RULE (BINDING): If ammonia was normal (<50 umol/L) at ANY earlier time point AND liver function has since recovered (INR < 1.5), ammonia is CONFIRMED normal. This is a PHYSIOLOGICAL CERTAINTY: a liver with normal synthetic function clears ammonia efficiently via the urea cycle. You MUST accept stale normal ammonia with recovered liver as current normal ammonia -- do NOT classify it as "unreliable" or "stale." IMPORTANT: Do NOT apply this rule before Day 5.
   - **CVVH CREATININE ARTIFACT:** When CVVH is active, creatinine is cleared by CRRT and may be artificially low. Do NOT count low creatinine during active CVVH as evidence of renal recovery.
   - **EARLY PRESENTATION WITHOUT TRAJECTORY (day 1-2):** When only 1-2 days of data are available, concordant recovery CANNOT be demonstrated because there is no trajectory. Do NOT assume recovery will occur based on ALFSG-PI alone. A high-severity day-1 presentation with deep HE (grade 3+) + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) is a near-KCC phenotype that the ALFSG-PI fundamentally underestimates (it excludes creatinine and ventilation). Without demonstrated recovery, predict death when this severity pattern is present.
   - **EARLY CRITICAL METABOLIC WARNING (Day 2-3 BINDING; Day 1 CONDITIONAL):** At Day 2-3, patients may show PARTIAL improvement (e.g., INR declining, creatinine improving) while retaining critical metabolic derangements that predict death. This check evaluates CURRENT VALUES, NOT trends. When ANY of the following are present at Day 2-3, predict DEATH regardless of other improvements: (a) ammonia >150 umol/L -- this is BINDING: ammonia >150 carries significant ICH risk REGARDLESS of whether it is declining. (b) lactate >4 mmol/L AND not declining, (c) bilirubin actively rising. DAY 1 EXCEPTION: At Day 1 ONLY, ammonia >150 is NOT binding if ALL of: (a) HE grade 0-1, (b) no mechanical ventilation, (c) no vasopressor support. On Day 1, ammonia is at presentation peak before NAC treatment; grade 0-1 HE means the brain is tolerating the load. At Day 2-3, ammonia >150 despite treatment IS binding. If Day 1 AND (HE grade 2+ OR ventilation OR vasopressors), ammonia >150 IS still binding. This is BINDING and FINAL at Day 2-3. This is distinct from Day 5+ demonstrated recovery where multi-day concordant improvement IS conclusive.
   - **DEMONSTRATED RECOVERY OVERRIDES INITIAL PROGNOSIS (Day 5+ ONLY, NOT Day 4, NEAR-CONCLUSIVE):** When a patient at Day 5+ shows clear hepatic recovery trajectory -- INR normalized to <1.5 (from initially elevated), ALT declined >80% from peak, AND bilirubin is declining (or already near-normal <3 mg/dL) -- the liver IS regenerating regardless of initial ALFSG-PI or etiology. STRICT BILIRUBIN: "declining" means the MOST RECENT trend is downward. If the vignette shows bilirubin as "Increasing" (even slightly), it is NOT declining. A bilirubin rebound is NOT declining. At Day 4, do NOT apply this rule. This is NEAR-CONCLUSIVE evidence of hepatic recovery that OVERRIDES the initial ALFSG-PI score. When demonstrated recovery criteria are met, predict SURVIVAL unless there is active clinical deterioration (rising lactate, new infections, hemodynamic collapse). The burden of proof shifts: you need evidence of ACTIVE DETERIORATION to predict death.
   - **PARTIAL RECOVERY (Day 5+):** When INR has improved >60% from peak AND the peak INR was >5.0, combined with ALT >80% down from peak AND at least one of: lactate normalized (<2 mmol/L), HE resolved to grade 0-1, or creatinine improving -- the liver IS regenerating even though INR has not yet reached <1.5. As a critical care physician, assess whether the remaining organ failures are manageable with ICU support. Predict SURVIVAL with partial recovery unless ACTIVE DETERIORATION (rising lactate AND worsening creatinine AND new infections -- not isolated single-organ worsening).
   - **STALE LAB VALUE CAUTION:** Some lab values may be from earlier days (indicated by "from day X"). Values more than 2 days old should be interpreted with significant caution, particularly lactate and ammonia which change rapidly. In a patient showing clear recovery at day 5+, a stale elevated lactate from early presentation should NOT override current improving trends. CONVERSELY: if ammonia was NORMAL at an earlier time AND liver function has since improved, the ammonia is almost certainly still normal or lower (recovered liver clears ammonia). Stale normal ammonia with improved liver = reinforced normal ammonia.
   - **APAP-SPECIFIC LACTATE CONTEXT:** In APAP ALF, extreme lactate elevation (even >15-20 mmol/L) may represent Type B lactic acidosis from NAPQI-induced mitochondrial dysfunction (NAD+ depletion), NOT circulatory failure. Distinguishing features: (a) hemodynamically STABLE (no vasopressors or stable), (b) pH improving or near-normal despite extreme lactate, (c) no clinical signs of shock. When extreme lactate coexists with hemodynamic stability and improving pH in APAP, do NOT automatically equate with tissue hypoperfusion. This is specific to APAP and does NOT apply to other etiologies.
   - **ISOLATED CREATININE WORSENING CONTEXT:** In APAP ALF, AKI often follows a delayed trajectory -- creatinine may worsen for 3-5 days after liver recovery begins due to acute tubular necrosis (ATN). Isolated creatinine worsening (without rising lactate, without hemodynamic collapse, without new infections) is a WEAKER deterioration signal than multi-organ worsening. When the liver has recovered and only creatinine is worsening, this is likely ATN progression that will recover with renal support. Do NOT classify isolated creatinine worsening as "active deterioration" when all other markers are stable or improving.

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
- **MANDATORY PRE-CHECK A -- UREMIC ENCEPHALOPATHY (BINDING, CHECK FIRST):** Before evaluating ANY override, check: Is grade 3-4 HE present AND ammonia normal (<50) AND creatinine >5 mg/dL? If ALL THREE true, HE is UREMIC, not hepatic. This is BINDING -- do NOT add extra conditions (CRRT status, ventilation, neurologic improvement, hepatic normalization are ALL IRRELEVANT). Hepatic HE REQUIRES hyperammonemia; normal ammonia + severe uremia = uremic coma. Uremic coma does NOT carry cerebral edema risk and is REVERSIBLE with renal replacement. The persistent HE death override is NULLIFIED. Record: "HE is uremic -- HE override nullified."
- **MANDATORY PRE-CHECK B -- EARLY CRITICAL METABOLIC WARNING (Day 2-3 BINDING; Day 1 CONDITIONAL):** At Day 2-3, check CURRENT VALUES (not trends): ammonia >150 AND/OR lactate >4 not declining AND/OR bilirubin rising = predict DEATH. This is BINDING and FINAL. CRITICAL: ammonia >150 means the CURRENT reading exceeds 150, regardless of decline from a higher value. Ammonia 152 (down from 487) STILL triggers this check. Do NOT rationalize declining ammonia as "improving" when it remains above the lethal threshold. DAY 1 EXCEPTION: At Day 1 ONLY, ammonia >150 is NOT binding if ALL of: (a) HE grade 0-1, (b) no mechanical ventilation, (c) no vasopressor support. On Day 1, ammonia is at presentation peak before NAC treatment; grade 0-1 HE means the brain is tolerating the load. If Day 1 AND (HE grade 2+ OR ventilation OR vasopressors), ammonia >150 IS still binding. Record: "Pre-Check B triggered: [values]. Predict death." OR "Day 1 exception applied: ammonia [value] but HE grade [X], no vent, no pressors -- monitoring."
- **MANDATORY PRE-CHECK C -- MECHANICAL VENTILATION AT DAY 1-3 (BINDING):** At Day 1-3, if the patient is receiving mechanical ventilation, this is a CRITICAL independent mortality predictor that ALFSG-PI does NOT capture. Predict DEATH. Rationale: Mechanical ventilation at Day 1-3 indicates disease severity (profound neurological compromise, aspiration risk, respiratory failure) beyond what laboratory trajectories can assess within 1-3 days. Even if hepatic markers are improving (INR declining, ALT down >70%, bilirubin decreasing), ventilator dependence at Day 1-3 represents a severity phenotype incompatible with spontaneous recovery. A favorable ALFSG-PI (even >80%) is UNRELIABLE when the patient requires ventilation because ALFSG-PI does not model ventilation status. Do NOT let improving liver labs override mechanical ventilation at Day 1-3. Record: "Pre-Check C triggered: mechanical ventilation at Day [X]. Predict death."
- **PRIORITY 1 -- DEMONSTRATED RECOVERY (Day 5+ ONLY, NOT Day 4):** If INR < 1.5, ALT >80% down, bilirubin declining (or <3 mg/dL), predict SURVIVAL unless active deterioration (rising lactate, new infections, hemodynamic collapse). Isolated creatinine worsening is NOT active deterioration. STRICT BILIRUBIN CHECK (BINDING): "bilirubin declining" means the MOST RECENT trend is downward. If the vignette reports bilirubin trend as "Increasing," bilirubin is NOT declining and Priority 1 is NOT met -- check Priority 1B and 1C next (they have DIFFERENT criteria). ONE EXCEPTION: non-uremic grade 4 HE with PaO2/FiO2 < 2.0. IMPORTANT: At Day 4, do NOT apply Priority 1/1B/1C -- evaluate persistent grade 4 HE override directly.
- **PRIORITY 1B -- PARTIAL RECOVERY (Day 5+, NO BILIRUBIN REQUIREMENT, BINDING):** INR >60% improved from peak >5.0 + ALT >80% down + lactate <2 or HE grade 0-1 or creatinine improving = liver regenerating. CALCULATING INR IMPROVEMENT: (peak - current) / peak. Example: peak 12 to 2.46 = 79.5% -- MEETS >60%. No requirement for resulting INR to be below any value. This does NOT require bilirubin declining. Rising bilirubin does NOT negate Priority 1B. Predict SURVIVAL unless ALL THREE present: rising lactate AND worsening creatinine AND new infections. Vasopressors and mechanical ventilation alone do NOT negate Priority 1B when lactate is normal (<2). Isolated creatinine worsening (even severe, e.g., 6.3 mg/dL) is ATN lag in APAP, NOT multi-organ deterioration. If Priority 1B criteria are met and ALL THREE negation criteria are NOT present, you MUST predict SURVIVAL.
- **PRIORITY 1C -- MODERATE-INR HEPATIC RECOVERY (Day 5+, BINDING):** Check: (a) peak INR 2.0-5.0, (b) ALT >80% down from peak, (c) lactate <=2 OR HE grade 0-1, (d) bilirubin lower than patient's OWN peak (declining from THEIR peak -- bilirubin 14.2 from peak 19.5 satisfies this). If ALL four met = liver regenerating. Predict SURVIVAL unless multi-organ active deterioration. BILIRUBIN LAG EXCEPTION (APAP ONLY): If (a), (b), (c) met but bilirubin still rising (not peaked yet), Priority 1C IS STILL MET if ALL of: HE 0-1, no vent, no pressors, no infection, creatinine stable/improving, AND lactate <=2.0 or declining to <=2.0. STALE LACTATE PROVISION: If the most recent available lactate was <=2.0 (even if from a prior day) AND no subsequent metabolic deterioration (no vasopressors added, no new infection, creatinine stable/improving, no acidosis), the stale lactate satisfies the <=2.0 requirement. In APAP hyperacute ALF, bilirubin excretory lag commonly continues days after synthetic recovery. When ALL other systems confirm recovery, rising bilirubin alone is lag, NOT failed regeneration.
- **COMBINATION SIGNAL:** When BOTH moderate-INR recovery (1C) AND uremic HE (Pre-Check A) apply, this is a STRONG survival signal: the liver is recovering AND the coma is non-hepatic/reversible.
- **PRIORITY 2 -- Only if NO recovery criteria met AND HE is NOT uremic:**
  (a) EXTREME BILIRUBIN (BINDING): Bilirubin >15 in APAP AND not declining = DEATH unless ALL of: HE 0-1, lactate <=2.0, no vent, no pressors, no infection. ANY discordance (HE 2+, lactate >2.0, vent, pressors, infection) = DEATH. Near-normal INR + declining ALT do NOT override extreme bilirubin with discordance.
  (b) Persistent non-uremic grade 4 HE at Day 4+ without full exception conditions = death. DAY 4 CRITICAL: At Day 4, this override is the PRIMARY evaluation because Priority 1/1B/1C are NOT available (Day 5+ only). Even with fully normalized liver labs, persistent grade 4 HE for 4 consecutive days + PaO2/FiO2 < 2.0 = DEATH from neurologic cause. Do NOT use low ammonia to dismiss grade 4 HE at Day 4 -- ammonia context rule is Day 5+ ONLY.
  (c) APAP LACTATE: OSCILLATING extreme lactate with hemodynamic stability = mitochondrial, not circulatory.
  (d) CVVH creatinine artifact.
- DISCORDANT pattern WITHOUT recovery AND without uremic HE = failed regeneration = death.

**Step 9: Make Final Prediction**
- FIRST: Apply Pre-Check C result. If Day 1-3 AND patient is on mechanical ventilation: predict DEATH immediately. This is BINDING. Mechanical ventilation at Day 1-3 is an independent mortality predictor not captured by ALFSG-PI.
- SECOND: Apply Pre-Check B result. If Day 2-3 AND ammonia >150 or lactate >4 not declining or bilirubin rising: predict DEATH immediately. This is BINDING. At Day 1, ammonia >150 is NOT binding if HE grade 0-1 + no vent + no pressors (Day 1 exception). DAY 1 EXCEPTION ENFORCEMENT: When the Day 1 exception IS active (ammonia >150 BUT HE 0-1 AND no vent AND no pressors), you MUST NOT use ammonia as the primary basis for predicting death. Day 1 ammonia is at presentation peak before NAC; HE 0-1 confirms brain tolerance. With favorable etiology (APAP) and ALFSG-PI >85% and no organ support, ammonia alone does NOT predict death at Day 1.
- THIRD: Apply Pre-Check A result. If HE is uremic, the HE death override is NULLIFIED. Do NOT let uremic grade 4 HE drive a death prediction.
- FOURTH: At Day 4 with persistent grade 4 HE + PaO2/FiO2 < 2.0 (and HE not uremic): predict DEATH. Priority 1/1B/1C require Day 5+.
- If ANY recovery criteria met (Priority 1/1B/1C including bilirubin lag exception at Day 5+) AND no multi-organ active deterioration: decision MUST be "Yes." For Priority 1B specifically: negation requires ALL THREE of rising lactate + worsening creatinine + new infections. Vasopressors, ventilation, rising bilirubin, and isolated creatinine worsening do NOT negate Priority 1B. For Priority 1C: if bilirubin is still rising but ALL other systems confirm recovery (HE 0-1, no vent, no pressors, no infection, creatinine OK, lactate <=2), the bilirubin lag exception applies. Remaining organ failures are ICU-manageable when the liver is recovering. STRICT BILIRUBIN: If bilirubin trend is "Increasing," Priority 1 specifically is NOT met -- but check Priority 1B and 1C (they have DIFFERENT criteria -- 1B has no bilirubin requirement, 1C has a bilirubin lag exception for APAP).
- COMBINATION: moderate-INR recovery + uremic HE = STRONG survival signal. Predict Yes.
- CRITICAL: When NO Priority 1/1B/1C criteria are formally met (including bilirubin lag exception), you CANNOT predict survival based on informal clinical impression. You MUST evaluate and apply Priority 2 death overrides. If bilirubin >15 AND not declining AND any discordance: predict DEATH.
- CRITICAL PEAK INR VERIFICATION: Before claiming ANY recovery criteria are met, verify peak INR: Priority 1B requires peak INR >5.0. Priority 1C requires peak INR 2.0-5.0. If peak INR <2.0, ONLY Priority 1 (INR <1.5 + ALT >80% + bilirubin declining) can apply. A patient with peak INR <2.0 AND bilirubin not declining has NO formal recovery criteria, regardless of how normalized the INR is.
- EXTREME BILIRUBIN ENFORCEMENT (BINDING, FINAL CHECK): Before outputting your prediction, if bilirubin is >15 mg/dL in APAP AND not declining AND NO formal recovery criteria (Priority 1/1B/1C) are met, verify: are ALL five exception conditions met (HE 0-1, lactate <=2.0, no mechanical ventilation, no vasopressors, no infection)? If ANY SINGLE exception is NOT met, you MUST predict DEATH. Normalized INR and declining ALT do NOT override this. This is NON-NEGOTIABLE.
- When Priority 1 criteria ARE met (INR <1.5, ALT >80% down, bilirubin declining at Day 5+): predict SURVIVAL. The ONLY exception is non-uremic grade 4 HE (NOT grade 3) with PaO2/FiO2 < 2.0. Mechanical ventilation alone, grade 3 HE alone, and severe creatinine/AKI alone are NOT grounds to override Priority 1.
- Only apply death overrides when: (a) Pre-Check B not triggered, AND (b) no recovery criteria met (1, 1B, or 1C), AND (c) HE is not uremic.

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
   - EXTREME BILIRUBIN (context-dependent): Bilirubin >15 mg/dL in APAP = typically catastrophic excretory failure (typical lag ~8-12 mg/dL). Predict death UNLESS full concordant recovery across ALL other systems (HE grade 0-1, INR < 1.5, lactate <=2.0, no vasopressors, no ventilation, no infections). If bilirubin >15 AND any other system shows discordance, predict death. IMPORTANT: If Priority 1C bilirubin lag exception applies (peak INR 2-5, ALT >80% down, HE 0-1, no vent, no pressors, no infection, creatinine OK, lactate <=2 in APAP), this is bilirubin excretory lag, NOT catastrophic failure -- predict survival.
   - PERSISTENT GRADE 4 HE (duration-based): APAP recovery clears HE within 2-3 days. Grade 4 HE persisting at Day 4+ in APAP (or Day 5+ in non-APAP) = predict death UNLESS ALL of these conditions are met: liver function fully normalized (INR < 1.5, bilirubin < 5 mg/dL, lactate < 2.0 mmol/L, no active infections, ALT declining) AND PaO2/FiO2 >= 2.0. These exception conditions are EXHAUSTIVE: if ALL met, exception applies REGARDLESS of vasopressors, ventilation, AKI, or elevated WBC. The ONLY features that strengthen this override are: lactate >2, bilirubin >5, documented infection, INR >1.5, PaO2/FiO2 <2.0. No other features apply. This override is SUPERSEDED by demonstrated recovery at Day 5+ (see Step 8, Priority 1). Grade 3 HE does NOT trigger this override.
   - AMMONIA CONTEXT FOR HE ASSESSMENT (Day 5+ ONLY): At Day 5+ in APAP (or Day 6+ in non-APAP), when persistent grade 3-4 HE coexists with NORMAL ammonia (<50 umol/L) AND there is an alternative explanation (uremia, sedation, ICU delirium), the coma is likely NON-hepatic. Do NOT trigger the persistent HE death override. STALE AMMONIA RULE (BINDING): If ammonia was normal (<50) at ANY earlier time AND liver has since recovered (INR < 1.5), ammonia is CONFIRMED normal -- a liver with normal synthetic function physiologically clears ammonia via the urea cycle. Do NOT classify as "unreliable." Do NOT apply before Day 5.
   - Low creatinine during active CVVH is NOT evidence of renal recovery -- CRRT clears creatinine.
   - **EARLY PRESENTATION WITHOUT TRAJECTORY (day 1-2):** When only 1-2 days of data are available, concordant recovery CANNOT be demonstrated because there is no trajectory. Do NOT assume recovery will occur based on ALFSG-PI alone. A high-severity day-1 presentation with deep HE (grade 3+) + mechanical ventilation + severe AKI (creatinine >= 3.4 mg/dL) is a near-KCC phenotype that the ALFSG-PI fundamentally underestimates (it excludes creatinine and ventilation). Without demonstrated recovery, predict death when this severity pattern is present.
   Be especially wary when ALFSG-PI improves at a single time point due to vasopressor cessation and HE improvement, but the overall trajectory shows discordance.
   - **EARLY CRITICAL METABOLIC WARNING (Day 2-3 BINDING; Day 1 CONDITIONAL):** At Day 2-3, patients may show PARTIAL improvement while retaining critical metabolic derangements. This check evaluates CURRENT VALUES, NOT trends. When ANY of the following are present at Day 2-3, predict DEATH regardless of other improvements: (a) ammonia >150 umol/L -- this is BINDING: ammonia >150 carries significant ICH risk REGARDLESS of whether it is declining. (b) lactate >4 mmol/L AND not declining, (c) bilirubin actively rising. DAY 1 EXCEPTION: At Day 1 ONLY, ammonia >150 is NOT binding if ALL of: (a) HE grade 0-1, (b) no mechanical ventilation, (c) no vasopressor support. On Day 1, ammonia is at presentation peak before NAC; grade 0-1 HE means brain is tolerating. At Day 2-3, ammonia >150 despite treatment IS binding. If Day 1 AND (HE grade 2+ OR ventilation OR vasopressors), ammonia >150 IS still binding. This is BINDING and FINAL at Day 2-3.
   - **DEMONSTRATED RECOVERY OVERRIDES INITIAL PROGNOSIS (Day 5+ ONLY, NOT Day 4, NEAR-CONCLUSIVE):** When a patient at Day 5+ shows clear hepatic recovery trajectory -- INR normalized to <1.5, ALT declined >80% from peak, AND bilirubin declining (or near-normal <3 mg/dL) -- the liver IS regenerating. STRICT BILIRUBIN: "declining" means the MOST RECENT trend is downward. If the vignette shows bilirubin as "Increasing," it is NOT declining. A bilirubin rebound is NOT declining. At Day 4, do NOT apply this rule. This is NEAR-CONCLUSIVE evidence of hepatic recovery that OVERRIDES the initial ALFSG-PI score. When demonstrated recovery criteria are met, predict SURVIVAL unless active clinical deterioration (rising lactate, new infections, hemodynamic collapse).
   - **PARTIAL RECOVERY (Day 5+):** When INR has improved >60% from peak AND peak was >5.0, combined with ALT >80% down AND at least one of: lactate normalized (<2), HE resolved to grade 0-1, or creatinine improving -- the liver IS regenerating even though INR has not yet reached <1.5. >30% of "too sick" patients survive (Dong 2024), especially when liver recovery is clear. Predict SURVIVAL unless ACTIVE DETERIORATION (multi-organ: rising lactate AND worsening creatinine AND new infections).
   - **STALE LAB VALUE CAUTION:** Lab values from earlier days (indicated by "from day X") more than 2 days old should be interpreted with caution, particularly lactate and ammonia. A stale elevated value from early presentation should NOT override current improving trends. CONVERSELY: if ammonia was NORMAL at an earlier time AND liver function has since improved, the ammonia is almost certainly still normal or lower (recovered liver clears ammonia). Stale normal ammonia with improved liver = reinforced normal ammonia.
   - **APAP-SPECIFIC LACTATE CONTEXT:** In APAP ALF, extreme lactate elevation may represent Type B lactic acidosis from NAPQI-induced mitochondrial dysfunction, NOT circulatory failure. When extreme lactate coexists with hemodynamic stability (no vasopressors or stable) and improving pH, do NOT automatically equate with tissue hypoperfusion or futility.
   - **ISOLATED CREATININE WORSENING CONTEXT:** In APAP ALF, AKI often worsens for 3-5 days after liver recovery begins (ATN lag). Isolated creatinine worsening (without rising lactate, without hemodynamic collapse, without new infections) is NOT sufficient to predict death when the liver is recovering. Renal failure in ALF is potentially reversible with CRRT support.

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
- **MANDATORY PRE-CHECK A -- UREMIC ENCEPHALOPATHY (BINDING, CHECK FIRST):** Before any override, check: grade 3-4 HE AND ammonia <50 AND creatinine >5? If ALL THREE true, HE is UREMIC, not hepatic. This is BINDING -- do NOT add extra conditions (CRRT status, ventilation, neurologic improvement, hepatic normalization are IRRELEVANT). Normal ammonia + severe uremia = uremic coma (does NOT carry cerebral edema risk, REVERSIBLE with dialysis). HE death override NULLIFIED. Record: "HE is uremic -- HE override nullified."
- **MANDATORY PRE-CHECK B -- EARLY METABOLIC WARNING (Day 2-3 BINDING; Day 1 CONDITIONAL):** At Day 2-3, check CURRENT VALUES (not trends): ammonia >150 AND/OR lactate >4 not declining AND/OR bilirubin rising = predict DEATH. This is BINDING and FINAL. CRITICAL: ammonia >150 means the CURRENT reading exceeds 150, regardless of decline from a higher value. Ammonia 152 (down from 487) STILL triggers this check. DAY 1 EXCEPTION: At Day 1 ONLY, ammonia >150 is NOT binding if ALL of: (a) HE grade 0-1, (b) no mechanical ventilation, (c) no vasopressor support. On Day 1, ammonia is at presentation peak before NAC treatment. If Day 1 AND (HE grade 2+ OR ventilation OR vasopressors), ammonia >150 IS still binding. DAY 1 EXCEPTION ENFORCEMENT: When the Day 1 exception IS active, you MUST NOT use ammonia as the primary basis for predicting death. HE 0-1 confirms brain tolerance despite elevated ammonia. With favorable etiology and ALFSG-PI >85% and no organ support, predict SURVIVAL at Day 1. Record: "Pre-Check B triggered: [values]. Predict death." OR "Day 1 exception applied."
- **MANDATORY PRE-CHECK C -- MECHANICAL VENTILATION AT DAY 1-3 (BINDING):** At Day 1-3, if the patient is receiving mechanical ventilation, this is a CRITICAL independent mortality predictor that ALFSG-PI does NOT capture. Predict DEATH. Rationale: Mechanical ventilation at Day 1-3 indicates disease severity (profound neurological compromise, aspiration risk, respiratory failure) beyond what laboratory trajectories can assess within 1-3 days. Even if hepatic markers are improving (INR declining, ALT down >70%, bilirubin decreasing), ventilator dependence at Day 1-3 represents a severity phenotype incompatible with spontaneous recovery. A favorable ALFSG-PI (even >80%) is UNRELIABLE when the patient requires ventilation because ALFSG-PI does not model ventilation status. Do NOT let improving liver labs override mechanical ventilation at Day 1-3. Record: "Pre-Check C triggered: mechanical ventilation at Day [X]. Predict death."
- **PRIORITY 1 -- DEMONSTRATED RECOVERY (Day 5+ ONLY, NOT Day 4):** INR < 1.5 + ALT >80% down + bilirubin declining (or <3) = liver regenerating. STRICT BILIRUBIN CHECK (BINDING): "bilirubin declining" means the MOST RECENT trend is downward. If the vignette shows bilirubin trend as "Increasing," bilirubin is NOT declining and Priority 1 is NOT met -- check Priority 1B and 1C next (they have DIFFERENT criteria). Predict SURVIVAL unless active deterioration. Isolated creatinine worsening NOT sufficient. >30% of "too sick" survive (Dong 2024). EXCEPTION: non-uremic grade 4 HE with PaO2/FiO2 < 2.0. At Day 4, do NOT apply Priority 1/1B/1C -- evaluate persistent grade 4 HE override directly.
- **PRIORITY 1B -- PARTIAL RECOVERY (Day 5+, NO BILIRUBIN REQUIREMENT, BINDING):** INR >60% improved from peak >5.0 + ALT >80% down + lactate <2 or HE 0-1 or creatinine improving = liver regenerating. CALCULATING INR IMPROVEMENT: (peak - current) / peak. Example: peak 12 to 2.46 = 79.5% -- MEETS >60%. No requirement for resulting INR to be below any value. This does NOT require bilirubin declining. Rising bilirubin does NOT negate Priority 1B. Predict SURVIVAL unless ALL THREE present: rising lactate AND worsening creatinine AND new infections. Vasopressors and mechanical ventilation alone do NOT negate Priority 1B when lactate is normal (<2). Isolated creatinine worsening (even severe, e.g., 6.3 mg/dL) is ATN lag in APAP, NOT multi-organ deterioration. If Priority 1B criteria are met and ALL THREE negation criteria are NOT present, you MUST predict SURVIVAL.
- **PRIORITY 1C -- MODERATE-INR RECOVERY (Day 5+, BINDING):** Peak INR 2.0-5.0 + ALT >80% down + lactate <=2 OR HE 0-1 + bilirubin declining from patient's OWN peak (any decline, regardless of absolute level) = liver regenerating. Predict SURVIVAL unless multi-organ active deterioration. BILIRUBIN LAG EXCEPTION (APAP ONLY): If first three criteria met but bilirubin still rising, Priority 1C IS STILL MET if ALL of: HE 0-1, no vent, no pressors, no infection, creatinine stable/improving, AND lactate <=2.0 or declining to <=2.0. STALE LACTATE PROVISION: If the most recent available lactate was <=2.0 (even if from a prior day) AND no subsequent metabolic deterioration (no vasopressors, no new infection, creatinine stable/improving, no acidosis), the stale lactate satisfies the <=2.0 requirement. Rising bilirubin with full concordant extrahepatic recovery = bilirubin excretory lag in APAP, NOT failed regeneration.
- **COMBINATION:** Moderate-INR recovery + uremic HE = STRONG survival signal. Liver recovering AND coma reversible.
- **PRIORITY 2 -- Only if NO recovery met AND HE NOT uremic:**
- EXTREME BILIRUBIN (BINDING): Bilirubin >15 in APAP AND not declining = DEATH unless ALL of: HE 0-1, lactate <=2.0, no vent, no pressors, no infection. ANY discordance (HE 2+, lactate >2.0, vent, pressors, infection) = DEATH. Near-normal INR + declining ALT do NOT override extreme bilirubin with discordance.
- Non-uremic persistent grade 4 HE at Day 4+ without exception conditions = death. DAY 4: This is the PRIMARY evaluation at Day 4 because Priority 1/1B/1C require Day 5+. Even with normalized liver labs, persistent grade 4 HE + PaO2/FiO2 < 2.0 at Day 4 = DEATH (neurologic risk). Do NOT use low ammonia to dismiss grade 4 HE at Day 4 -- ammonia context rule is Day 5+ ONLY.
- APAP LACTATE: OSCILLATING extreme lactate with hemodynamic stability = mitochondrial.
- Discordant WITHOUT recovery AND without uremic HE = death.
- PRE-CHECK C (BINDING): At Day 1-3, if the patient is on mechanical ventilation, predict DEATH immediately. This is an independent mortality predictor not captured by ALFSG-PI. Improving liver labs do NOT override ventilator dependence at Day 1-3.
- BINDING: When any recovery criteria met at Day 5+ (including Priority 1C bilirubin lag exception), decision MUST be "Yes" unless SPECIFIC MULTI-ORGAN worsening. For Priority 1B specifically: negation requires ALL THREE of rising lactate + worsening creatinine + new infections. Vasopressors, ventilation, rising bilirubin, and isolated creatinine worsening do NOT negate Priority 1B. For Priority 1C: bilirubin lag exception applies in APAP when bilirubin is rising but ALL other systems confirm recovery (HE 0-1, no vent, no pressors, no infection, creatinine OK, lactate <=2). STRICT BILIRUBIN: If bilirubin trend is "Increasing," Priority 1 specifically is NOT met -- but Priority 1B has no bilirubin requirement and Priority 1C has a bilirubin lag exception. CRITICAL: When NO Priority 1/1B/1C criteria are formally met (including bilirubin lag exception), you MUST evaluate and apply Priority 2 death overrides. Do NOT predict survival based on informal recovery impression.
- EXTREME BILIRUBIN ENFORCEMENT (BINDING, FINAL CHECK): Before outputting your prediction, if bilirubin is >15 mg/dL in APAP AND not declining AND NO formal recovery criteria (Priority 1/1B/1C) are met, verify: are ALL five exception conditions met (HE 0-1, lactate <=2.0, no mechanical ventilation, no vasopressors, no infection)? If ANY SINGLE exception is NOT met (e.g., ventilation IS present, OR HE IS grade 2+, OR lactate is stale/unknown), you MUST predict DEATH. Normalized INR and declining ALT do NOT override this. This is NON-NEGOTIABLE.
- CRITICAL PEAK INR VERIFICATION: Before claiming recovery, verify peak INR: Priority 1B requires peak INR >5.0. Priority 1C requires peak INR 2.0-5.0. If peak INR <2.0, ONLY Priority 1 (INR <1.5 + ALT >80% + bilirubin declining) can apply. A patient with peak INR <2.0 AND bilirubin not declining has NO formal recovery criteria.
- When Priority 1 criteria ARE met (INR <1.5, ALT >80% down, bilirubin declining at Day 5+): predict SURVIVAL. The ONLY exception is non-uremic grade 4 HE (NOT grade 3) with PaO2/FiO2 < 2.0. Mechanical ventilation alone, grade 3 HE alone, and severe creatinine/AKI alone are NOT grounds to override Priority 1.

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

**OVERRIDE CONDITIONS (EVALUATE IN PRIORITY ORDER):**

**MANDATORY PRE-CHECK A -- UREMIC ENCEPHALOPATHY (BINDING, CHECK FIRST):**
Before evaluating ANY override, extract from specialist reasoning: Is grade 3-4 HE present AND ammonia normal (<50) AND creatinine >5 mg/dL? If ALL THREE true, the HE is UREMIC, not hepatic. This is BINDING and FINAL -- do NOT add extra conditions (CRRT status, ventilation, neurologic improvement, hepatic normalization are ALL IRRELEVANT). Hepatic HE REQUIRES hyperammonemia; normal ammonia + severe uremia = uremic coma. The persistent HE death override is NULLIFIED for this patient. Record: "HE is uremic -- HE override nullified."

**MANDATORY PRE-CHECK B -- EARLY METABOLIC WARNING (Day 2-3 BINDING; Day 1 CONDITIONAL):**
At Day 2-3, check CURRENT VALUES (not trends): ammonia >150 AND/OR lactate >4 not declining AND/OR bilirubin rising = predict DEATH. This is BINDING and FINAL. CRITICAL: ammonia >150 means the CURRENT reading exceeds 150, regardless of decline from a higher value. Ammonia 152 (down from 487) is STILL >150 and STILL triggers this check. DAY 1 EXCEPTION: At Day 1 ONLY, ammonia >150 is NOT binding if ALL of: (a) HE grade 0-1, (b) no mechanical ventilation, (c) no vasopressor support. Rationale: on Day 1, ammonia is at presentation peak before NAC treatment; grade 0-1 HE means the brain is tolerating the ammonia load. If Day 1 AND (HE grade 2+ OR ventilation OR vasopressors), ammonia >150 IS still binding.
BILIRUBIN RISING EXCEPTION (Day 2-3 ONLY): If "bilirubin rising" is the ONLY Pre-Check B trigger (i.e., ammonia <=150 or NOT REPORTED, AND lactate <=4 or declining) AND ALL of the following are true: (a) INR has improved >50% from peak, (b) HE grade 0-1, (c) no mechanical ventilation, (d) no vasopressor support, (e) lactate <=2.0 (including stale lactate from a prior day via the Stale Lactate Provision -- a Day 2 lactate of 2.0 IS valid for Day 3 evaluation; also note: 2.0 EQUALS <=2.0, this condition IS satisfied) -- then Pre-Check B is WAIVED. There is NO "current-value rule," NO "same-day requirement," and NO requirement that lactate be from the CURRENT evaluation day. The Stale Lactate Provision explicitly covers prior-day values. If lactate was 2.0 on Day 2, it IS <=2.0 for Day 3 evaluation -- do NOT reject it by claiming it is "not a current Day 3 value." MISSING AMMONIA RULE: If ammonia is NOT reported in the clinical data, it is assumed to NOT trigger Pre-Check B (i.e., treated as <=150). If ammonia were dangerously elevated, it would be reported. Absence of ammonia data means ammonia is not a concern and does NOT block the bilirubin rising exception. Follow the weighted vote instead. Rationale: In APAP hyperacute ALF, bilirubin excretory lag commonly causes rising bilirubin at Day 2-3 even as INR dramatically recovers (e.g., INR 10.7 to 1.8 = 83% improvement). When INR recovery demonstrates active liver regeneration AND no organ support is needed AND HE is minimal, isolated rising bilirubin is excretory lag, NOT metabolic failure. Predicting death solely on rising bilirubin when all other markers confirm recovery is a false positive.
WORKED EXAMPLE (BILIRUBIN RISING EXCEPTION): Day 3, APAP, INR 10.7->1.8 (83% improvement, >50%), bilirubin 7.6->9.5 (rising), ammonia not reported (MISSING AMMONIA RULE: treated as <=150), lactate 2.0 from Day 2 (Stale Lactate Provision: Day 2 lactate IS valid for Day 3; there is NO "current-value rule" requiring Day 3 lactate; 2.0 = <=2.0), HE grade 1 (0-1), no vent, no pressors, ALFSG-PI 86.5%. Step 1: Only Pre-Check B trigger is "bilirubin rising" (ammonia not reported = <=150, lactate <=4). Step 2: INR 83% improvement >50%. Step 3: HE grade 1, no vent, no pressors, lactate 2.0 via stale provision. Step 4: ALL exception conditions met -- Pre-Check B is WAIVED. Step 5: All 3 specialists predict Yes. Weighted vote = SURVIVAL. If you are tempted to reject the Day 2 lactate because it is "not a current Day 3 value" -- STOP. The Stale Lactate Provision explicitly makes prior-day lactate valid. There is no same-day requirement.

**MANDATORY PRE-CHECK C -- MECHANICAL VENTILATION AT DAY 1-3 (BINDING):**
At Day 1-3, if the patient is receiving mechanical ventilation, predict DEATH. This is BINDING and FINAL. Mechanical ventilation at Day 1-3 is a CRITICAL independent mortality predictor that ALFSG-PI does NOT capture. Even if specialists vote Yes based on improving liver labs (INR declining, ALT down), ventilator dependence at Day 1-3 represents disease severity incompatible with spontaneous recovery. This override takes priority over the weighted vote at Day 1-3.

**DAY 4 PERSISTENT GRADE 4 HE RULE (BINDING):**
At Day 4, Priority 1/1B/1C recovery criteria are NOT available (they require Day 5+). If persistent grade 4 HE AND PaO2/FiO2 < 2.0 AND HE is NOT uremic at Day 4: predict DEATH regardless of liver recovery metrics. Even with INR 1.0 and fully recovered liver, 4 consecutive days of grade 4 coma + respiratory failure carries independent neurologic death risk (cerebral edema/herniation -- 28% of ALF deaths are neurologic). Do NOT use low ammonia to dismiss grade 4 HE at Day 4 -- the ammonia context rule is Day 5+ ONLY. The Hepatologist may predict survival based on liver recovery, but liver recovery does NOT prevent neurologic death.

**PRIORITY 1 -- DEMONSTRATED RECOVERY (Day 5+ ONLY, NOT Day 4, BINDING):**
If ALL THREE are met: (a) INR < 1.5, (b) ALT >80% down from peak, (c) bilirubin declining (or <3 mg/dL) -- then Priority 1 IS MET. Predict SURVIVAL. THESE THREE CRITERIA ARE EXHAUSTIVE -- no additional "systemic recovery markers," "concordance," or "supportive evidence" is required. When INR <1.5 AND ALT >80% down AND bilirubin declining, the liver IS regenerating regardless of other organ status.
STRICT BILIRUBIN CHECK: "bilirubin declining" means the MOST RECENT trend is downward. Example: 14.3->10.5 IS declining. Example: 15.5->15.8 is NOT declining. Example: 5.5->7.2->7.8 is NOT declining (rising). A bilirubin REBOUND is NOT declining. If bilirubin is not declining, Priority 1 is NOT met -- even if INR <1.5 and ALT >80% down, ALL THREE criteria must be satisfied. When bilirubin is rising, Priority 1 FAILS and you MUST check Priority 1B, 1C, and then Rules 5B and 6. Do NOT treat "near-normal INR + declining ALT + rising bilirubin" as informal recovery -- without meeting ALL THREE Priority 1 criteria, you have NO formal recovery, and death overrides (Rule 5B for non-uremic grade 4 HE, Rule 6 for extreme bilirubin) MUST be evaluated.
MANDATORY SEQUENCE AFTER RECOVERY CRITERIA FAIL: If you check Priorities 1, 1B, and 1C and NONE are met, you MUST proceed to check Rules 5B (non-uremic grade 4 HE) and 6 (Extreme Bilirubin) BEFORE making any prediction. Do NOT skip to the weighted vote. Do NOT engage in free-form clinical reasoning about "favorable trajectory" or "dominant physiologic recovery." When formal recovery criteria are not met, favorable lab trends (improving INR, declining ALT) do NOT substitute for formal criteria. The ONLY valid path when all recovery criteria fail is: check Rule 5B, check Rule 6, and if neither fires, THEN follow the weighted vote.
NEGATION: ONLY non-uremic grade 4 HE (specifically grade 4, NOT grade 3) with PaO2/FiO2 < 2.0 can negate Priority 1. Mechanical ventilation alone, grade 3 HE alone, severe AKI (even creatinine >5), CVVH, and elevated non-declining creatinine do NOT negate Priority 1. These are ICU complications manageable when the liver is regenerating.
WORKED EXAMPLE: Day 7 patient with INR 1.33, ALT down 95% from peak, bilirubin declining (14.3->10.5). Also: mechanical ventilation, grade 3 HE, creatinine 7.6, CVVH. Priority 1 IS MET: (a) INR 1.33 <1.5 = YES, (b) ALT 95% >80% = YES, (c) bilirubin 14.3->10.5 = declining = YES. Predict SURVIVAL. Ventilation + grade 3 HE + creatinine 7.6 + CVVH do NOT negate. No "systemic recovery markers" or "concordance" needed beyond these three.
INDEPENDENT ASSESSMENT: Even if ALL specialists predict "No," review their clinical data for ALL recovery criteria (Priority 1, 1B, AND 1C). A unanimous "No" does NOT override clinical reality. If Priority 1 is met by the data, predict SURVIVAL regardless of specialist votes.

**PRIORITY 1B -- PARTIAL RECOVERY (Day 5+, NO BILIRUBIN REQUIREMENT, BINDING):**
INR >60% improved from peak >5.0 + ALT >80% down + lactate <2 or HE 0-1 or creatinine improving = liver regenerating. CALCULATING INR IMPROVEMENT: percentage = (peak_INR - current_INR) / peak_INR. Example: peak 12.0 to current 2.46 = (12.0 - 2.46)/12.0 = 79.5% -- this MEETS >60%. There is NO requirement for the resulting INR to be below any specific value (2.0, 1.5, etc.) -- only that the improvement percentage exceeds 60%. This does NOT require bilirubin to be declining (unlike Priority 1). >30% "too sick" survive. Predict SURVIVAL unless ALL THREE present: rising lactate AND worsening creatinine AND new infections. CRITICAL: Vasopressors and mechanical ventilation alone do NOT negate Priority 1B when lactate is normal (<2). Isolated creatinine worsening (even severe, e.g., 6.3) is ATN lag in APAP, NOT multi-organ deterioration. Rising bilirubin does NOT negate 1B (no bilirubin requirement). If Priority 1B is met and ALL THREE negation criteria are NOT present, you MUST predict SURVIVAL regardless of how the specialists voted.

**PRIORITY 1C -- MODERATE-INR RECOVERY (Day 5+, BINDING):**
Peak INR 2.0-5.0 + ALT >80% down + lactate <=2 OR HE 0-1 + bilirubin declining from patient's OWN peak (any decline, regardless of absolute level -- e.g., 19.5 to 14.2 satisfies "declining") = liver regenerating. Predict SURVIVAL. The ONLY negation for 1C is rising lactate AND worsening creatinine AND new infections (all three required). Isolated creatinine worsening (even severe), mechanical ventilation, or persistent HE (especially if uremic) do NOT negate 1C.
BILIRUBIN LAG EXCEPTION (APAP ONLY, BINDING): If the first three criteria (peak INR 2-5, ALT >80% down, lactate <=2 or HE 0-1) are met but bilirubin is STILL RISING (has not peaked yet), Priority 1C IS STILL MET if ALL of: HE grade 0-1, no mechanical ventilation, no vasopressor support, no documented infection, creatinine stable or improving (MOST RECENT trend -- a creatinine that went up then came down, e.g. 3.9->5.4->3.7, IS "improving" because the latest direction is downward; non-monotonic trajectories that are currently declining count as improving), AND lactate <=2.0 or declining to <=2.0. STALE LACTATE PROVISION (BINDING): If the most recent available lactate was <=2.0 (even if from a prior day, e.g., Day 3 lactate of 2.0 when evaluating Day 6) AND there has been no subsequent metabolic deterioration (no vasopressors added, no new infection, creatinine stable/improving, no acidosis), the stale lactate satisfies the <=2.0 requirement. Do NOT reject stale lactate by saying "cannot be verified," "not contemporaneous," "cannot safely assume," or any similar hedging language -- the provision explicitly covers non-contemporaneous lactate values. Rising bilirubin does NOT invalidate stale lactate; bilirubin is an excretory marker, NOT a metabolic marker, and its trend is irrelevant to lactate validity. The ONLY things that invalidate stale lactate are: new vasopressors, new infection, worsening creatinine, or new acidosis since the lactate measurement. Rationale: lactate reflects hepatic/systemic metabolic function; if it was normal and no deterioration occurred since, it remains physiologically valid. In APAP hyperacute ALF, bilirubin excretory lag commonly continues rising for days after synthetic function (INR) recovers. When ALL other organ systems confirm recovery (no organ support, resolved HE, normal renal function, low lactate), rising bilirubin alone is excretory lag, NOT failed regeneration. If the bilirubin lag exception applies, predict SURVIVAL regardless of specialist votes.
WORKED EXAMPLE (STALE LACTATE + BILIRUBIN LAG): Day 6, APAP, peak INR 3.96 (2-5 range = 1C applicable), ALT >80% down, HE grade 0, no vent, no pressors, no infection, creatinine stable. Bilirubin 16.5 still rising (not peaked yet). Last lactate was 2.0 on Day 3 with no subsequent deterioration. Step 1: Stale Lactate Provision applies -- Day 3 lactate of 2.0 IS valid for Day 6. Step 2: All bilirubin lag exception conditions met (HE 0-1, no vent, no pressors, no infection, creatinine stable, lactate <=2.0 via stale provision). Step 3: Priority 1C IS MET via bilirubin lag exception. Step 4: Predict SURVIVAL regardless of specialist votes or bilirubin level.

**COMBINATION SIGNAL (BINDING, ABSOLUTE, OVERRIDES ALL EXTRAHEPATIC CONCERNS):** When BOTH moderate-INR recovery (1C criteria met: peak INR 2-5, ALT >80% down, lactate <=2, bilirubin declining from peak) AND uremic HE (Pre-Check A: grade 3-4 HE + ammonia <50 + creatinine >5) apply: predict SURVIVAL. This is BINDING and ABSOLUTE -- no extrahepatic findings can override it. The worsening creatinine IS the cause of the uremic coma and is NOT "multi-organ deterioration" -- it is the EXPECTED pattern in uremic encephalopathy. Mechanical ventilation in uremic coma is airway protection for the comatose patient, NOT evidence of respiratory failure or hepatic non-recovery. Absence of CVVH/RRT is a treatment timing decision, NOT evidence that the patient cannot recover. DO NOT apply "multi-organ active deterioration," "extrahepatic organ failure," "uncontrolled systemic dysfunction," or ANY similar framing to negate this combination signal. DO NOT invent additional requirements beyond the 1C criteria + uremic HE definition listed here. If 1C criteria are met AND uremic HE is confirmed, the answer is SURVIVAL -- full stop.
WORKED EXAMPLE: Day 7, APAP. 1C: peak INR 2.9 (2-5), ALT >80% down, lactate 1.3, bilirubin 19.5->14.2. Uremic HE: grade 4 coma + ammonia 45 (<50) + creatinine 9.8 (>5). Also: on vent, no CVVH, all 3 specialists predict No. Result: SURVIVAL. The vent is airway protection for uremic coma. The creatinine 9.8 is the CAUSE of the coma. No CVVH is irrelevant to liver recovery. 3/3 No votes are overridden by this BINDING rule.

**PRIORITY 2 -- Only if NO recovery criteria met (including 1C bilirubin lag exception) AND HE NOT uremic:**
- EXTREME BILIRUBIN (BINDING): Bilirubin >15 in APAP AND not declining = DEATH unless ALL of: HE 0-1, lactate <=2.0, no vent, no pressors, no infection. ANY discordance (HE 2+, lactate >2.0, vent, pressors, infection) = DEATH. Near-normal INR + declining ALT do NOT override this. When Hepatologist says "liver is recovering" but bilirubin >15 with discordance AND no formal Priority 1/1B/1C met: predict DEATH.
- NON-UREMIC PERSISTENT GRADE 4 HE (BINDING): At Day 5+, if patient has persistent grade 4 coma AND HE is NOT uremic (ammonia >=50 OR creatinine <=5) AND NO formal Priority 1/1B/1C recovery criteria are met: predict DEATH. Persistent grade 4 coma without formal hepatic recovery criteria signals ongoing cerebral injury with high mortality risk. Even if INR is near-normal and ALT is falling, the absence of formal recovery criteria (e.g., bilirubin still rising or INR not yet <1.5) combined with ongoing deep coma = death. Documented infection further compounds this risk. Do NOT override with the weighted vote -- this is BINDING.
- NEAR-KCC WITHOUT TRAJECTORY (day 1-2) = death.
- APAP LACTATE (BINDING): OSCILLATING extreme lactate (going up AND down, not steadily rising) with hemodynamic stability (no vasopressors or stable on vasopressors) = Type B lactic acidosis from APAP mitochondrial dysfunction, NOT circulatory failure. When lactate oscillates AND patient has no vasopressors AND liver recovery criteria are met (Priority 1/1B/1C), lactate does NOT override survival prediction. Do NOT predict death based on elevated lactate alone when it is oscillating with hemodynamic stability.
- CRITICAL ENFORCEMENT: When NO Priority 1/1B/1C criteria are formally met, you CANNOT predict survival based on informal recovery impression regardless of how good INR/ALT look. "Close to meeting criteria" is NOT meeting criteria -- 54% INR improvement is not >60%, and 74% ALT decline is not >80%. You MUST apply Priority 2 overrides if conditions are met. Even if all 3 specialists predict Yes and INR is clearly improving, if formal thresholds are not reached and bilirubin >15 with discordance, Extreme Bilirubin DEATH override takes precedence.

**SYNTHESIS RULES (apply in order -- PRE-CHECKS FIRST):**
1. **Pre-Check C (BINDING at Day 1-3):** If Day 1-3 AND patient is on mechanical ventilation: predict DEATH. Mechanical ventilation at Day 1-3 is an independent mortality predictor not captured by ALFSG-PI. Even if specialists vote Yes based on improving liver labs, ventilator dependence at Day 1-3 overrides. This takes priority over the weighted vote.
1B. **Pre-Check B (BINDING at Day 2-3; CONDITIONAL at Day 1):** If Day 2-3 AND ammonia >150 or lactate >4 not declining or bilirubin rising: predict DEATH. At Day 1, ammonia >150 NOT binding if HE 0-1 + no vent + no pressors. A declining ammonia that is still >150 is STILL dangerous at Day 2-3. If ammonia is NOT reported in the clinical data, it is treated as NOT triggering Pre-Check B. BILIRUBIN RISING EXCEPTION (Day 2-3 ONLY): If the ONLY Pre-Check B trigger is "bilirubin rising" (ammonia <=150 or not reported, AND lactate <=4 or declining) AND INR has improved >50% from peak AND HE grade 0-1 AND no mechanical ventilation AND no vasopressor support AND lactate <=2.0 (including stale lactate from a prior day -- a Day 2 lactate of 2.0 IS valid for Day 3; there is NO "current-value rule" or "same-day requirement"; 2.0 equals <=2.0): Pre-Check B is WAIVED. Rationale: In APAP, bilirubin excretory lag commonly causes rising bilirubin at Day 2-3 even as INR dramatically recovers. When INR recovery demonstrates liver regeneration and no organ support is needed, isolated rising bilirubin is excretory lag, NOT metabolic failure. Follow the weighted vote instead.
2. **Pre-Check A:** If HE is uremic (grade 3-4 HE + ammonia <50 + creatinine >5): the HE death override is NULLIFIED. Assess liver trajectory independently.
2B. **Day 4 Rule (BINDING):** At Day 4, Priority 1/1B/1C are NOT available. If persistent grade 4 HE + PaO2/FiO2 < 2.0 + HE not uremic: predict DEATH regardless of liver recovery. Hepatologist liver recovery assessment does NOT override neurologic death risk at Day 4.
3. If ANY recovery criteria met (Priority 1, 1B, or 1C including bilirubin lag exception at Day 5+ ONLY) AND no multi-organ active deterioration: predict SURVIVAL regardless of weighted vote. For Priority 1: the ONLY exception is non-uremic grade 4 HE (NOT grade 3) with PaO2/FiO2 < 2.0. Mechanical ventilation alone, grade 3 HE alone, and severe creatinine/AKI alone (even creatinine >5) are NOT grounds to override Priority 1 -- these are ICU-manageable when the liver is regenerating. For Priority 1B specifically: negation requires ALL THREE of rising lactate + worsening creatinine + new infections. Vasopressors/ventilation alone do NOT negate 1B when lactate is normal. Isolated creatinine worsening is ATN lag. Rising bilirubin does NOT negate 1B. STRICT BILIRUBIN applies ONLY to Priority 1: if bilirubin trend is "Increasing," Priority 1 is NOT met -- but check Priority 1B and 1C (they have DIFFERENT criteria). For Priority 1C: if bilirubin is still rising but ALL other systems confirm recovery (HE 0-1, no vent, no pressors, no infection, creatinine OK, lactate <=2), the bilirubin lag exception makes 1C met -- predict SURVIVAL.
4. If Hepatologist identifies liver recovery AND predicts survival AND Day 5+: give DECISIVE weight. NOT applicable at Day 4 with persistent grade 4 HE. When bilirubin is rising, verify if Priority 1B or 1C (including bilirubin lag exception) criteria are met before dismissing recovery.
5. COMBINATION (BINDING, OVERRIDES ALL EXTRAHEPATIC CONCERNS): If Priority 1C criteria met (peak INR 2-5, ALT >80% down, lactate <=2, bilirubin declining from peak) AND uremic HE (Pre-Check A: grade 3-4 HE + ammonia <50 + creatinine >5): predict SURVIVAL. This is ABSOLUTE and FINAL. The multi-organ deterioration check is WAIVED. DO NOT override this rule by citing mechanical ventilation, severe AKI, lack of RRT/CVVH, hemodynamic support, or ANY extrahepatic organ failure. In uremic coma, ventilator dependence is airway protection for coma (NOT respiratory failure), profound AKI is the CAUSE of the coma (NOT a separate organ failing), and absence of CVVH/RRT is a treatment decision, NOT evidence of non-recovery. Even if ALL specialists predict No, this combination overrides. DO NOT invent terms like "uncontrolled extrahepatic organ failure" or "severe multi-system dysfunction" to circumvent this rule -- the rule already accounts for these findings.
WORKED EXAMPLE (COMBINATION SIGNAL): Day 7, APAP, peak INR 2.9 (2-5 range), ALT >80% down, lactate 1.3 (<=2), bilirubin 19.5->14.2 (declining from peak). HE: grade 4 coma, ammonia 45 (<50), creatinine 9.8 (>5) = uremic HE confirmed. Also: mechanical ventilation, no CVVH. Step 1: 1C criteria -- peak INR 2.9 (2-5), ALT >80% down, lactate 1.3, bilirubin declining = ALL MET. Step 2: Uremic HE -- grade 4 + ammonia 45 <50 + creatinine 9.8 >5 = CONFIRMED. Step 3: Combination Signal = BINDING SURVIVAL. Step 4: Vent + creatinine 9.8 + no CVVH = EXPECTED in uremic coma, NOT grounds to override. Predict SURVIVAL. If you are tempted to say "but the patient has severe extrahepatic organ failure" -- STOP. That IS the uremic coma pattern this rule explicitly covers.
5B. **NON-UREMIC GRADE 4 HE DEATH OVERRIDE (BINDING, MANDATORY CHECK at Day 5+ when NO recovery criteria met):** WHEN TO CHECK: After evaluating Priorities 1, 1B, and 1C and finding NONE met, you MUST check this rule BEFORE making any prediction. Do NOT skip to the weighted vote. Do NOT engage in free-form clinical reasoning about "favorable trajectory," "dominant physiologic recovery," or "recovery more likely than not." When formal recovery criteria are not met, improving INR and declining ALT do NOT substitute for formal criteria -- they are NECESSARY but NOT SUFFICIENT for a survival prediction. The ONLY valid path when all recovery criteria fail is to check Rules 5B and 6. RULE: If persistent grade 4 coma AND HE is NOT uremic (ammonia >=50 OR creatinine <=5) AND NO formal Priority 1/1B/1C recovery criteria are met: predict DEATH regardless of weighted vote. Persistent non-uremic grade 4 coma without hepatic recovery criteria = ongoing cerebral injury. Even near-normal INR and falling ALT do NOT override this when formal criteria (bilirubin trend, etc.) are not met. Documented infection further compounds mortality risk. CRITICAL: If INR <1.5 and ALT >80% down BUT bilirubin is RISING, Priority 1 is NOT met (requires all three). Two out of three criteria met does NOT count as recovery. You MUST apply Rule 5B if grade 4 coma is present and non-uremic. Do NOT rationalize around this by citing "improving trajectory," "favorable labs," "ALFSG-PI prognosis," or "lack of shock physiology" -- none of these override Rule 5B.
WORKED EXAMPLE (5B OVERRIDES 3/3 YES WITH NEAR-NORMAL INR): Day 7, APAP, INR 1.47 (<1.5), ALT 90% down (>80%), bilirubin 5.5->7.2->7.8 (RISING, not declining). Grade 4 coma, ammonia 73.5 (>=50 = NOT uremic), documented infection. ALFSG-PI 79%. No vasopressors, no rising lactate, improving creatinine. Step 1: Priority 1 -- INR <1.5 YES, ALT >80% down YES, bilirubin declining NO (rising). Priority 1 = NOT MET (2 of 3 is NOT 3 of 3). Step 2: Priority 1B -- peak INR 3.48, not >5.0 = NOT APPLICABLE. Priority 1C -- peak INR 3.48 is in 2-5 range but bilirubin is rising and bilirubin lag exception requires HE 0-1 (patient has grade 4) = NOT MET. Step 3: No formal recovery criteria met. MANDATORY: proceed to Rule 5B. Step 4: Rule 5B -- persistent grade 4 coma + ammonia 73.5 >=50 (not uremic) + no formal recovery + infection = DEATH. Even though INR is nearly normal and ALT is 90% down and 2/3 specialists predict Yes and ALFSG-PI is 79% and there are no vasopressors -- without ALL THREE Priority 1 criteria met, there is NO formal recovery, and Rule 5B fires. Do NOT rationalize with "the dominant physiologic trajectory is favorable" or "recovery more likely than not" -- formal criteria are formal criteria. If you are tempted to predict survival because the labs look good -- STOP. Check Rule 5B. Grade 4 coma + no formal recovery + infection = DEATH.
6. **EXTREME BILIRUBIN ENFORCEMENT (BINDING, OVERRIDES WEIGHTED VOTE):** MANDATORY PRE-CHECK: BEFORE applying this rule, verify whether the BILIRUBIN LAG EXCEPTION makes Priority 1C met. If peak INR is 2-5 AND ALT >80% down AND (lactate <=2 OR HE 0-1) AND ALL bilirubin lag exception conditions are satisfied (HE 0-1, no vent, no pressors, no infection, creatinine stable or improving per MOST RECENT trend, lactate <=2 including via Stale Lactate Provision), then 1C IS MET via bilirubin lag exception and this Extreme Bilirubin rule DOES NOT FIRE -- predict SURVIVAL per Rule 3. "Creatinine improving" means the most recent direction is downward (e.g., 3.9->5.4->3.7 = improving because 5.4->3.7 is declining). Only proceed with Extreme Bilirubin if the bilirubin lag exception does NOT apply.
PEAK INR VERIFICATION: Priority 1B requires peak INR >5.0. Priority 1C requires peak INR 2.0-5.0. If peak INR is <2.0, NEITHER 1B NOR 1C can be invoked -- only Priority 1 (which requires bilirubin declining). A patient with peak INR <2.0 AND bilirubin not declining has NO formal recovery criteria regardless of INR normalization. NEAR-MISS DOES NOT COUNT: If INR improvement is 54% (below 60%) or ALT decline is 74% (below 80%), Priority 1B is NOT met even though it is "close." Formal criteria require STRICT threshold adherence -- 59% improvement is NOT >60%, and 79% ALT decline is NOT >80%. Do NOT treat near-miss as "likely recovery" or "trajectory toward recovery" -- if thresholds are not met, no formal criteria are met, and Extreme Bilirubin MUST be applied.
If bilirubin >15 in APAP AND not declining AND NO formal recovery criteria (Priority 1/1B/1C including bilirubin lag exception) are met: check the five exception conditions (HE 0-1, lactate <=2.0, no vent, no pressors, no infection). If ANY SINGLE exception FAILS (HE 2+, lactate >2.0, vent present, pressors present, infection present): predict DEATH regardless of how specialists voted (even 3/3 Yes). Normalized INR and declining ALT do NOT override extreme bilirubin with discordance. HOWEVER: If ALL FIVE exception conditions ARE met (HE 0-1, lactate <=2.0, no vent, no pressors, no infection), the Extreme Bilirubin rule is WAIVED -- follow the weighted vote. Rationale: bilirubin >15 with a completely benign extrahepatic profile (no organ support, no encephalopathy, no infection) is excretory lag in a recovering patient, not failed regeneration.
WORKED EXAMPLE 1 (EXTREME BILI OVERRIDES 3/3 YES): Day 7, APAP, bilirubin 15.5->15.8 (>15, not declining), INR 1.3 (normalized), ALT >90% down. BUT: mechanical ventilation + HE grade 2 + severe AKI. Priority 1 NOT met (bilirubin not declining). Priority 1B NOT met (peak INR <5). Exception check: HE grade 2 = FAILS HE 0-1 condition. RESULT: Extreme Bilirubin BINDING DEATH even though all 3 specialists predict Yes. The vent + HE grade 2 discordance overrides the normalized INR/ALT.
WORKED EXAMPLE 2 (NEAR-MISS RECOVERY DOES NOT SAVE): Day 7, APAP, peak INR 5.2, current INR 2.38, ALT 1847->482 (74% down), bilirubin 18 and rising, HE grade 2, on mechanical ventilation + CVVH, no vasopressors, lactate 1.46. Step 1: Priority 1 -- INR not <1.5, bilirubin not declining = NOT MET. Step 2: Priority 1B -- peak INR 5.2 >5.0, so 1B applicable. INR improvement = (5.2-2.38)/5.2 = 54.2%. This is BELOW >60% threshold. ALT 74% down is BELOW >80% threshold. Priority 1B = NOT MET (even though "close"). Step 3: Priority 1C -- peak INR 5.2 is NOT in 2.0-5.0 range = NOT APPLICABLE. Step 4: NO formal recovery criteria met. Step 5: Extreme Bilirubin check -- bilirubin 18 (>15), rising, APAP. Exception check: HE grade 2 FAILS (need 0-1). Mechanical ventilation FAILS (need no vent). Step 6: RESULT = Extreme Bilirubin BINDING DEATH. Even though INR is "improving" and ALT is "declining" and all 3 specialists vote Yes -- when formal criteria are not met and bilirubin >15 with discordance, predict DEATH.
6B. APAP LACTATE CONTEXT (BINDING): When lactate is extreme but OSCILLATING (going up AND down, not steadily rising) AND patient has no vasopressors or is hemodynamically stable, this is Type B mitochondrial lactic acidosis, NOT circulatory failure. If recovery criteria (Priority 1/1B/1C) are met AND lactate is oscillating with hemodynamic stability, lactate does NOT override the survival prediction. Do NOT predict death based on oscillating lactate when the liver is recovering and hemodynamics are stable.
7. **Day 1-3 EARLY ASSESSMENT RULE (BINDING):** At Day 1-3, no formal recovery criteria (Priority 1/1B/1C) are available. If Pre-Check C is triggered (mechanical ventilation), predict DEATH regardless of weighted vote. If Pre-Check B is triggered (and the Bilirubin Rising Exception does NOT apply), predict DEATH. DAY 1 FAVORABLE OVERRIDE: At Day 1 specifically, if Pre-Check B Day 1 exception is active (ammonia >150 BUT HE 0-1 AND no vent AND no pressors) AND the Hepatologist predicts Yes AND ALFSG-PI >85%: predict SURVIVAL regardless of CC/TS votes. Rationale: The Hepatologist is the liver specialist, and their favorable assessment at Day 1 with high ALFSG-PI and no organ support outweighs CC/TS concerns about ammonia when the Day 1 exception explicitly makes ammonia non-binding. CC and TS often vote No based on ammonia risk despite the exception -- this override corrects that bias. If neither Pre-Check B nor C is triggered AND no Day 1 favorable override applies AND no other binding override applies, follow the WEIGHTED VOTE. The ONLY exceptions at Day 1-3 that can override the weighted vote are: binding Pre-Check B death override, binding Pre-Check C death override, and the Day 1 favorable survival override above.
8. Otherwise: follow the weighted vote. IMPORTANT: You may ONLY reach this step if NO binding rule above (Pre-Checks, Priorities, Rules 5B, 6) has been triggered. If you find yourself here while the patient has grade 4 HE and no formal recovery criteria -- STOP, you have skipped Rule 5B. Go back and check."""

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
        
        # The Committee Chair's LLM output is the final prediction.
        # Do NOT override with weighted_decision -- the Committee Chair
        # is designed to override the weighted vote when clinical criteria
        # (demonstrated recovery, death overrides) warrant it.

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
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'agent_predictions_{args.deployment}_{timestamp}.xlsx'
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

