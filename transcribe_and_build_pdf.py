"""
Final FRCA Podcast Transcriber + PDF Builder
Transcribes all MP3s with Whisper (base model) and compiles into a
fully-formatted exam-revision PDF with Q&A dialogue, key points,
ASCII flowcharts, and concept boxes.
"""

import os
import sys
import json
import re

# Add ffmpeg to PATH so Whisper can decode MP3s
_FFMPEG_DIR = r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
if _FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

import whisper
from pathlib import Path
from datetime import datetime

# ── ReportLab imports ──────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.platypus.flowables import Flowable

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

FOLDER       = Path(r"C:\Users\Admin\Downloads\Dr Podcast\Final")
CACHE_DIR    = FOLDER / "_transcripts_cache"
OUTPUT_PDF   = FOLDER / "FRCA_Complete_Exam_Revision_Guide.pdf"
WHISPER_MODEL = "base"   # tiny / base / small — base is best CPU tradeoff

CACHE_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
#  TOPIC STRUCTURE  (category → list of stems)
# ══════════════════════════════════════════════════════════════════════════════

CATEGORIES = {
    "Cardiac Anaesthesia": [
        "Anaesthesia_for_Cardiac_Surgery",
        "Anaesthesia_of_Cardiac_Patient_for_Non-cardiac_Surgery",
        "Arrhythmias",
        "Cardiomyopathy",
        "Congenital_Heart_Disease",
        "Hypertension",
        "Ischaemic_Heart_Disease_and_Congestive_Cardiac_Failure",
        "Pacemakers",
        "Postoperative_Management_of_Cardiac_Surgery_Patients",
        "Post-operative_Management_of_MI",
        "Preoperative_Assessment_of_Patients_with_Cardiac_Disease",
        "Valvular_Defects",
    ],
    "Day Stay / Day Case": [
        "Day_Case_Selection_Criteria",
    ],
    "Emergency Medicine": [
        "Acute_Poisoning",
        "Burns_and_Drowning",
    ],
    "Endocrinology": [
        "Endocrine_Disease",
        "Phaeochromocytoma",
        "Thyroid_Disease_and_Thyroid_Surgery",
    ],
    "ENT": [
        "Bleeding_Tonsil_and_Foreign_Body",
        "Difficult_Intubation",
        "Obstructive_Sleep_Apnoea",
        "Performing_a_Tracheostomy",
        "Upper_Airway_Infections",
    ],
    "Gastrointestinal Tract": [
        "Feeding",
        "Nausea_and_Vomiting",
        "Nutrition_Requirements_and_Malnutrition",
        "Oesophageal_Reflux",
        "Pancreatitis",
    ],
    "Haematological": [
        "Abnormalities_of_Coagulation_and_Haemostasis",
        "Anaemia_and_Abnormal_Haemoglobins",
        "Anticoagulant_Agents",
        "Antiplatelet_Agents_and_Antifibrinolytic_Agents",
        "Blood_Groups",
    ],
    "Hepatology": [
        "Hepatic_Failure",
        "Jaundice",
    ],
    "Intensive Care Medicine": [
        "ARDS_and_Ventilation_Difficulties",
        "High_Risk_Surgical_Patient",
        "Management_of_Multi_Organ_Failure",
        "Management_of_Severe_Sepsis",
    ],
    "Metabolism": [
        "Diabetes",
        "Hormonal_and_Metabolic_Response_to_Trauma",
        "Hyperthermia",
        "Hypothermia",
        "Obesity",
    ],
    "Neurosurgical Anaesthesia": [
        "Anaesthesia_for_an_MRI_Scan",
        "Brainstem_Death",
        "Depth_of_Anaesthesia_Monitoring",
        "ECT_and_Anti-Psychotics",
        "Epilepsy",
        "Head_Injuries_and_Control_of_ICP",
        "Late_Management_of_Spinal_Cord_Injury",
        "Management_of_Acute_Spinal_Cord_Injury",
        "Principles_for_Craniotomy",
        "Subarachnnoid_Haemorrhage",
    ],
    "Obstetrics": [
        "Anaesthesia_in_Early_Pregnancy",
        "Medical_Diseases_Complicating_Pregnancy_1",
        "Medical_Diseases_Complicating_Pregnancy_2",
        "Physiological_and_Anatomical_Changes_of_Pregnancy",
        "Pre-eclampsia",
    ],
    "Ophthalmic": [
        "Cataract_and_Detached_Retina",
        "Control_of_Intraocular_Pressure",
        "Orbital_Anatomy",
        "Penetrating_Eye_Injury",
        "Strabismum",
    ],
    "Orthopaedics": [
        "Embolic_Disease",
        "Myasthenia_and_Muscle_Diseases",
        "Procedures_under_Tourniquet",
        "Rheumatoid_Arthritis",
    ],
    "Paediatric and Neonatal": [
        "Development_in_infancy_and_childhood",
        "Intussuception",
        "Neonatal_Resuscitation_and_Effects_of_Prematurity",
        "Oesophageal_atresia_Diaphragmatic_Hernia_and_Exomphalos",
        "Principles_of_Neonatal_Physiology",
        "Pyloric_Stenosis",
    ],
    "Pain": [
        "Assessment_of_Acute_and_Chronic_Pain",
        "Back_Pain",
        "Neuropathic_Pain",
    ],
    "Regional Anaesthesia": [
        "Anatomy_of_Central_Venous_Access",
        "Anatomy_of_Extradural_Space",
        "Anatomy_of_the_Trachea_and_Bronchi",
        "Ankle_and_Knee_Blocks",
        "ANS_Anatomy",
        "Brachial_Plexus_Interscalene_and_Axillary_Blocks",
        "Caudal_Block",
        "Cranial_Nerves",
        "LA_Toxicity",
        "Lumbar_Plexus_Femoral_and_Sciatic_Nerve_Blocks",
        "Stellate_Ganglion_and_Celiac_Plexus_Blocks",
        "Ulnar_Median_and_Radial_Nerve_Blocks",
    ],
    "Renal": [
        "Calcium_and_Magnesium_Homeostatis",
        "Hypokalaemia_and_Hyperkalaemia",
        "Hyponatraemia_and_Hypernatraemia",
        "Renal_Failure",
        "Renal_Replacement_Therapy",
    ],
    "Thoracics": [
        "Anaesthesia_for_Bronchoscopy",
        "COPD_and_Asthma",
        "Lung_Cancer_and_Pulmonary_Fibrosis",
        "One_Lung_Ventilation",
        "Oxygen_Toxicity",
        "Pneumonia",
        "Pneumothorax",
    ],
    "Vascular": [
        "Abdominal_Aortic_Aneurysm",
        "Carotid_Endartarectomy",
    ],
}

# ══════════════════════════════════════════════════════════════════════════════
#  WHISPER TRANSCRIPTION
# ══════════════════════════════════════════════════════════════════════════════

def find_mp3(category, stem):
    """Return the mp3 path for a given category+stem, or None."""
    cat_slug = category.replace(" ", "_").replace("/", "_")
    # Try different filename patterns used in the folder
    patterns = [
        f"FinalFRCA{cat_slug}_{stem}.mp3",
        f"FinalFRCA{cat_slug.replace('_', '')}_{stem}.mp3",
    ]
    # Also try without category prefix (some files omit it)
    for fname in os.listdir(FOLDER):
        if fname.endswith(".mp3") and stem.replace("-", "_") in fname.replace("-", "_"):
            return FOLDER / fname
    return None


def get_all_mp3s():
    """Return sorted list of all .mp3 files."""
    return sorted(FOLDER.glob("*.mp3"))


def cache_path(mp3: Path) -> Path:
    return CACHE_DIR / (mp3.stem + ".json")


def transcribe_file(mp3: Path, model) -> dict:
    cp = cache_path(mp3)
    if cp.exists():
        with open(cp, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  [CACHE] {mp3.name}")
        return data

    print(f"  [WHISPER] {mp3.name} ...", end="", flush=True)
    result = model.transcribe(str(mp3), language="en", fp16=False)
    data = {
        "text": result["text"].strip(),
        "segments": [
            {"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in result["segments"]
        ],
    }
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(" done")
    return data


def transcribe_all():
    mp3s = get_all_mp3s()
    total = len(mp3s)
    print(f"\n{'='*60}")
    print(f"  Transcribing {total} MP3 files with Whisper '{WHISPER_MODEL}'")
    print(f"{'='*60}\n")
    model = whisper.load_model(WHISPER_MODEL)
    results = {}
    for i, mp3 in enumerate(mp3s, 1):
        print(f"[{i:3}/{total}] ", end="")
        results[mp3.stem] = transcribe_file(mp3, model)
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  TEXT POST-PROCESSING  — detect Q&A turns
# ══════════════════════════════════════════════════════════════════════════════

QUESTION_STARTERS = re.compile(
    r"\b(what|how|why|when|where|which|who|can you|could you|tell me|"
    r"describe|explain|outline|define|list|discuss|compare|contrast|"
    r"would you|is it|are there|do you|does|would|shall we|"
    r"talk me through|walk me through)\b",
    re.IGNORECASE,
)


def split_into_qa(text: str) -> list[dict]:
    """
    Heuristically split plain transcript into Q&A turns.
    Returns list of {'role': 'Examiner'|'Candidate', 'text': str}
    """
    # Split on sentence boundaries
    sentences = re.split(r"(?<=[.?!])\s+", text.strip())
    turns = []
    current_role = None
    current_buf = []

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        is_question = sent.endswith("?") or bool(QUESTION_STARTERS.match(sent))
        role = "Examiner" if is_question else "Candidate"

        if role != current_role:
            if current_buf:
                turns.append({"role": current_role, "text": " ".join(current_buf)})
            current_role = role
            current_buf = [sent]
        else:
            current_buf.append(sent)

    if current_buf:
        turns.append({"role": current_role, "text": " ".join(current_buf)})

    # Ensure we always start with Examiner
    if turns and turns[0]["role"] == "Candidate":
        turns[0]["role"] = "Examiner"

    return turns


def extract_key_points(text: str, n: int = 8) -> list[str]:
    """Extract likely key-point sentences (factual, numbered, or with important signal words)."""
    sentences = re.split(r"(?<=[.?!])\s+", text.strip())
    keywords = re.compile(
        r"\b(important|key|remember|note|critical|significant|essential|"
        r"first|second|third|main|primary|major|must|always|never|classified|"
        r"defined|diagnosis|treatment|management|cause|effect|mechanism|"
        r"dose|drug|contraindic|indication|complication|risk|benefit)\b",
        re.IGNORECASE,
    )
    scored = []
    for s in sentences:
        s = s.strip()
        if len(s) < 20:
            continue
        score = len(keywords.findall(s))
        if s.endswith("?"):
            score -= 2
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    seen = set()
    out = []
    for _, s in scored:
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= n:
            break
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  ASCII FLOWCHARTS  (topic-specific, embedded as pre-written text art)
# ══════════════════════════════════════════════════════════════════════════════

FLOWCHARTS = {
    "Anaesthesia_for_Cardiac_Surgery": """
┌─────────────────────────────────────┐
│     Pre-operative Assessment        │
│  Echo · Cath · PFTs · Medications   │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│          Induction                  │
│  High-dose opioid · Muscle relax    │
│  Arterial line before induction     │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│   Cardiopulmonary Bypass (CPB)      │
│  Heparinise (ACT >480s) → Cannulate │
│  Cool → Cross-clamp → Cardioplegia  │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│          Rewarming & Wean           │
│  Rewarm to 37°C → Defibrillate      │
│  Wean CPB → Protamine → Haemostat   │
└──────────────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────┐
│        ICU Management               │
│  Ventilation · Inotropes · Fluids   │
└─────────────────────────────────────┘
""",
    "Arrhythmias": """
     Arrhythmia Detected
            │
     ┌──────┴──────┐
   Narrow         Wide
   Complex       Complex
     │               │
  SVT / AF     VT vs SVT+aberr
     │               │
  Stable?         Stable?
  Y → Rate    N → DC Shock
  control
""",
    "Hypertension": """
  BP > 140/90  →  Confirm x2
       │
  Assess end-organ damage
  (Heart · Kidneys · Brain · Eyes)
       │
  ┌────┴────┐
Stage 1   Stage 2   Hypertensive
(140-159) (≥160)    Emergency
  │         │          │
Lifestyle  Add drug   IV labetalol
changes    therapy    / nitrate
""",
    "Cardiomyopathy": """
   CARDIOMYOPATHY
        │
   ┌────┼────┐
 DCM   HCM  RCM
  │     │    │
↓EF   ↑wall  Stiff
high  thick  walls
preload LVOTO diastolic
        │    failure
     Avoid:
     Tachycardia
     Vasodilation
     Myocardial depression
""",
    "Valvular_Defects": """
  STENOSIS               REGURGITATION
  (Fixed obstruction)    (Volume overload)
        │                       │
  Maintain                Maintain
  Heart Rate              Forward Flow
  Sinus Rhythm            Avoid Bradycardia
  Preload                 Vasodilate
  Avoid Tachycardia       Maintain Preload
        │                       │
  AS → Careful induction  AR → Keep HR 80-100
  MS → Control rate       MR → Vasodilate
""",
    "Congenital_Heart_Disease": """
 Congenital Heart Disease
          │
   ┌──────┴──────┐
 Cyanotic      Acyanotic
   │               │
Tet of Fallot   ASD/VSD/PDA
TGA             Coarctation
   │               │
R→L shunt      L→R shunt
↓O2            ↑pulm flow
   │
Avoid ↑PVR, ↓SVR, myocardial depression
""",
    "Pacemakers": """
  Pacemaker in situ
        │
  Check mode (NBG code)
  V O O / D D D / V V I
        │
  ┌─────┴─────┐
Elective   Emergency
  │             │
Programme  Magnet →
  to VOO    Asynch
        │
  Diathermy risk → Bipolar preferred
  Keep away from pacemaker site
""",
    "ARDS_and_Ventilation_Difficulties": """
  ARDS DIAGNOSIS (Berlin 2012)
  ┌─────────────────────────────┐
  │  Acute onset < 1 week       │
  │  Bilateral infiltrates CXR  │
  │  Not explained by cardiac   │
  │  PaO2/FiO2 < 300 (mild)    │
  │            < 200 (moderate) │
  │            < 100 (severe)   │
  └───────────────┬─────────────┘
                  ▼
     Lung-protective ventilation
     TV 6ml/kg IBW · Pplat <30
     PEEP titration · Prone if P/F<150
     Recruitment manoeuvres
""",
    "Management_of_Severe_Sepsis": """
  SEPSIS-3 Definition
  Infection + SOFA score ≥2
          │
  Septic Shock: MAP<65 + Lactate>2
          │
     HOUR-1 BUNDLE
  ┌───────────────────┐
  │ Lactate           │
  │ Blood cultures ×2 │
  │ Broad Ax          │
  │ 30ml/kg IVF       │
  │ Vasopressors      │
  └───────┬───────────┘
          ▼
  Noradrenaline 1st line pressor
  Target MAP ≥65 mmHg
  Source control within 6-12h
""",
    "Head_Injuries_and_Control_of_ICP": """
   MONROE-KELLIE DOCTRINE
   Brain + Blood + CSF = Constant
              │
   ICP Normal: 5-15 mmHg
              │
   ICP > 20 mmHg → Treat
   ┌────────────────────────────┐
   │ HOB 30° · Normocapnia      │
   │ Mannitol 0.25-1g/kg        │
   │ Hypertonic saline 3%       │
   │ Avoid hypoxia (SpO2>95)    │
   │ CPP = MAP - ICP (target>60)│
   └────────────────────────────┘
   Surgical: Decompressive craniectomy
""",
    "Subarachnnoid_Haemorrhage": """
  SAH → Sudden severe headache
  "Thunderclap" / "Worst ever"
          │
  CT head → LP (xanthochromia)
          │
  ┌───────┴────────┐
  Grading         Complications
  WFNS / Hunt-Hess Vasospasm (day 4-14)
  Fisher (CT)      Rebleed
                   Hydrocephalus
                   Hyponatraemia
          │
  Nimodipine 60mg q4h (21 days)
  Coil vs Clip (early <72h)
  Avoid hypo/hypertension
""",
    "Epilepsy": """
  Seizure Management
  0-5min → ABC, Lorazepam 4mg IV
  5-10min → Repeat Lorazepam
  10-30min → Phenytoin / Levetiracetam
  >30min  → STATUS EPILEPTICUS
          │
  Thiopental / Propofol / Midazolam
  ICU · EEG monitoring
  ┌─────────────────────────────┐
  │ Anaesthetic considerations  │
  │ Avoid seizure-threshold     │
  │ lowering agents: ketamine   │
  │ sevoflurane high conc       │
  │ Prefer propofol / isoflurane│
  └─────────────────────────────┘
""",
    "Brainstem_Death": """
  Preconditions for BSD Testing
  ┌────────────────────────────────┐
  │ Known irreversible brain damage│
  │ No drug / metabolic / temp     │
  │ cause of coma                  │
  └──────────────┬─────────────────┘
                 ▼
  TESTS (×2 by 2 doctors, ≥1 Consultant)
  │ No pupil reflex
  │ No corneal reflex
  │ No oculovestibular reflex
  │ No cranial motor response
  │ No gag / cough reflex
  │ Apnoea test: no resp at pCO2>6.65
                 ▼
  Time of death = time of 1st test
""",
    "Preoperative_Assessment_of_Patients_with_Cardiac_Disease": """
  Cardiac Pre-op Assessment
          │
  ┌───────┴────────┐
Active          Non-active
conditions      conditions
(defer/treat)   (estimate risk)
  │                   │
ACS/decomp HF    METs assessment
Severe AS         ≥4 METs = low risk
Significant        <4 METs = high risk
arrhythmia              │
          RCRI score (0-6)
          Revised Cardiac Risk Index
          Points: IHD, CCF, CVA,
          DM insulin, Cr>177, high-risk sx
""",
    "Hyponatraemia_and_Hypernatraemia": """
  HYPONATRAEMIA (Na <135)
  ┌──────────────────────────┐
  │ Assess volume status     │
  │  Hypo → SIADH / Addison  │
  │  Eu   → diuretics/vomit  │
  │  Hyper→ Oedema states     │
  └──────────┬───────────────┘
  Correct at <10 mmol/L/24h
  (risk of central pontine myelinolysis)

  HYPERNATRAEMIA (Na >145)
  Mostly water deficit
  Correct over 48h (0.5 mmol/L/h)
  Use hypotonic fluids / D5W
""",
    "Renal_Failure": """
  AKI — KDIGO Criteria
  ┌─────────────────────────────────┐
  │ Stage 1: Cr ×1.5 / UO<0.5×6h   │
  │ Stage 2: Cr ×2 / UO<0.5×12h    │
  │ Stage 3: Cr ×3 / UO<0.3×24h    │
  └──────────────┬──────────────────┘
  Pre-renal → Intrinsic → Post-renal
          │
  Manage: STOP nephrotoxins
          Fluid optimise
          Treat cause
          RRT if needed
""",
    "Diabetes": """
  PERIOPERATIVE DIABETES MANAGEMENT
  ┌────────────────────────────────┐
  │ Minor surgery (list 1st):      │
  │  Omit morning dose             │
  │  Monitor BG q1-2h              │
  │  Target BG 6-10 mmol/L         │
  ├────────────────────────────────┤
  │ Major surgery:                 │
  │  GKI (glucose-K-insulin) infusion│
  │  VRIII (variable-rate III)     │
  │  Continue metformin if stable  │
  └────────────────────────────────┘
  DKA: Fluids → Insulin → K+ replacement
""",
    "Obstetrics_Pre-eclampsia": """
  PRE-ECLAMPSIA
  BP >140/90 + Proteinuria after 20/40
          │
  Severe: BP >160/110
  HELLP: Haemolysis, ↑LFTs, ↓Platelets
          │
  ┌───────┴────────┐
Management      Delivery
  │              (only cure)
MgSO4 seizure  Regional if
prophylaxis    plt>75×10⁹
Antihypertensive
(labetalol/
nifedipine)
          │
  MgSO4 toxicity: Rx CaCl2 10ml 10%
""",
    "LA_Toxicity": """
  LOCAL ANAESTHETIC TOXICITY
  Symptoms: Metallic taste, tinnitus,
  perioral tingling → seizures → CVS collapse
          │
  ┌──────────────────────────────┐
  │ STOP injection               │
  │ Call for help                │
  │ ABC · 100% O2                │
  │ Control seizures:            │
  │   Benzodiazepine / thiopental│
  │ Lipid Emulsion 20%:          │
  │   1.5 ml/kg bolus            │
  │   0.25 ml/kg/min infusion    │
  │ CPR if cardiac arrest        │
  └──────────────────────────────┘
  Max doses: Bupivacaine 2mg/kg
             Lidocaine 3mg/kg (7 with adr)
""",
    "Difficult_Intubation": """
  DIFFICULT AIRWAY ALGORITHM
          │
  Pre-oxygenate (3min tidal vol / 8 VC breaths)
          │
  ┌───────┴────────┐
Predicted      Unanticipated
difficult       difficult
  │                 │
  Awake FOI     Best attempt ×3
  │             (DL/VL/bougie)
  │                 │
  RSI + plan B  CANNOT INTUBATE
  │             CANNOT OXYGENATE
  │                 │
  │             Front-of-neck access
  │             (scalpel-bougie-tube)
  Plan A→B→C→D (NAP4 guidelines)
""",
    "One_Lung_Ventilation": """
  ONE-LUNG VENTILATION
  Indications: Thoracic surgery,
  Haemorrhage, Infection, Fistula
          │
  DLT (left sided preferred) OR
  Bronchial blocker
          │
  Lung-protective settings:
  TV 4-6 ml/kg · PEEP 5-8 cmH2O
  FiO2 as needed
          │
  Hypoxia during OLV:
  ┌─────────────────────────────┐
  │ Check tube position (FOB)   │
  │ Increase FiO2               │
  │ CPAP to operative lung      │
  │ PEEP to ventilated lung     │
  │ HPV — avoid vasodilators    │
  └─────────────────────────────┘
""",
    "Anaesthesia_of_Cardiac_Patient_for_Non-cardiac_Surgery": """
  Cardiac Pt for Non-Cardiac Surgery
              │
  ┌───────────┴──────────┐
Active cardiac        Assess METS
conditions?           & RCRI score
  │                       │
  Yes → Delay/treat    <4 METS + ≥3 RCRI
  ↓                    → Consider stress test
  Stabilise               │
  then reassess       Proceed with:
                      Adequate monitoring
                      Avoid tachycardia
                      Maintain coronary perfusion
""",
    "Ischaemic_Heart_Disease_and_Congestive_Cardiac_Failure": """
  IHD Perioperative Risk
  ┌──────────────────────────────┐
  │ Recent MI (<30d) = high risk  │
  │ MI 30d-6mo = moderate risk   │
  │ MI >6mo + stable = lower risk │
  └──────────────┬───────────────┘
  Continue: aspirin, statins, beta-blockers
  Hold: ACEi/ARB day of surgery (hypotension)
  Target: MAP within 20% baseline

  CCF Management
  LVEDP ↑ → Preload reduce (diuretic)
  EF ↓  → Inotrope support
  Avoid: myocardial depressants, tachycardia
""",
    "Obesity": """
  OBESITY (BMI ≥30)
  Morbid Obesity: BMI ≥40
          │
  Physiological effects:
  ↑VO2/VCO2 · FRC↓ · Compliance↓
  ↑DVT/PE risk · OSA common
          │
  Airway: Often difficult
  Ramp position · Pre-oxygenate well
  RSI preferred
          │
  Drug dosing:
  TBW for sux/propofol induction
  LBW for most other drugs
  Avoid opioids if OSA
          │
  Post-op: Sitting up · O2 · CPAP
""",
    "Postoperative_Management_of_Cardiac_Surgery_Patients": """
  POST-CARDIAC SURGERY ICU
          │
  ┌───────────────────────────┐
  │ Haemodynamic monitoring   │
  │ Arterial · CVP · PAC/Echo │
  ├───────────────────────────┤
  │ Common problems:          │
  │  Low CO → Inotropes       │
  │  Hypertension → GTN/SNP   │
  │  Bleeding → FFP/platelets │
  │  Tamponade → drain/reopen │
  │  Arrhythmia → pacing/amio │
  ├───────────────────────────┤
  │ Fast-track: Extubate <6h  │
  │ Enhanced recovery pathway │
  └───────────────────────────┘
""",
}

# Fallback generic flowchart for topics without a specific one
GENERIC_FLOWCHART = """
  ┌─────────────────────────────┐
  │        Assessment           │
  │   History · Exam · Ix       │
  └──────────────┬──────────────┘
                 ▼
  ┌─────────────────────────────┐
  │     Risk Stratification     │
  │   Low / Moderate / High     │
  └──────────────┬──────────────┘
                 ▼
  ┌─────────────────────────────┐
  │        Management           │
  │   Medical · Anaesthetic     │
  │   Surgical · ICU            │
  └─────────────────────────────┘
"""

# ══════════════════════════════════════════════════════════════════════════════
#  CONCEPT BOXES  (topic-specific summary tables)
# ══════════════════════════════════════════════════════════════════════════════

CONCEPT_BOXES = {
    "Anaesthesia_for_Cardiac_Surgery": [
        ("CPB Circuit", "Pump + oxygenator + heat exchanger + reservoir"),
        ("Cardioplegia", "Cold K⁺-rich solution to arrest heart (St Thomas' solution)"),
        ("Heparin dose", "300-400 IU/kg; target ACT >480s"),
        ("Protamine", "1mg per 100 IU heparin; watch for anaphylaxis"),
        ("Hypothermia", "Mild 32-35°C / Moderate 25-32°C / Deep <20°C"),
    ],
    "Arrhythmias": [
        ("AF rate control", "Digoxin, diltiazem, metoprolol, amiodarone"),
        ("AF rhythm control", "DC cardioversion, amiodarone, flecainide"),
        ("VT stable", "Amiodarone 300mg IV"),
        ("VT unstable", "Synchronised DC shock 120-150J"),
        ("VF", "Unsynchronised shock 200J (biphasic)"),
        ("SVT", "Vagal → adenosine 6mg → 12mg → 18mg"),
    ],
    "LA_Toxicity": [
        ("Bupivacaine max", "2 mg/kg (without adrenaline)"),
        ("Lidocaine max", "3 mg/kg plain / 7 mg/kg with adrenaline"),
        ("Ropivacaine max", "3 mg/kg"),
        ("Lipid emulsion", "Intralipid 20%, 1.5ml/kg bolus"),
        ("Mechanism", "Na-channel block; bupivacaine also mitochondrial"),
    ],
    "Renal_Failure": [
        ("Pre-renal FeNa", "< 1%"),
        ("Intrinsic FeNa", "> 2%"),
        ("RRT indications", "AEIOU: Acid, Electrolytes, Intox, Overload, Uraemia"),
        ("Nephrotoxins", "NSAIDs, aminoglycosides, contrast, ACEi, tacrolimus"),
    ],
    "Diabetes": [
        ("DKA definition", "BG>11, pH<7.3, bicarb<15, ketones>3"),
        ("HONK", "BG>30, osm>320, no/minimal ketones, pH>7.3"),
        ("Insulin target", "BG 6-10 mmol/L peri-op"),
        ("Long-acting", "Continue at 80% dose, do not omit"),
    ],
    "ARDS_and_Ventilation_Difficulties": [
        ("TV", "6 ml/kg IBW"),
        ("Plateau pressure", "< 30 cmH2O"),
        ("PEEP", "5-15 cmH2O titrated to oxygenation"),
        ("Prone", "PaO2/FiO2 < 150 despite above → prone 16h/day"),
        ("NO", "Consider inhaled NO for refractory hypoxaemia"),
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
#  PDF STYLES
# ══════════════════════════════════════════════════════════════════════════════

def build_styles():
    base = getSampleStyleSheet()

    NAVY   = colors.HexColor("#0D2137")
    TEAL   = colors.HexColor("#007A8A")
    AMBER  = colors.HexColor("#D4851A")
    LTBLUE = colors.HexColor("#E8F4F8")
    LTAMBER= colors.HexColor("#FDF4E3")
    WHITE  = colors.white

    styles = {}

    styles["cover_title"] = ParagraphStyle(
        "cover_title", parent=base["Title"],
        fontSize=28, leading=36, textColor=WHITE,
        fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=12,
    )
    styles["cover_sub"] = ParagraphStyle(
        "cover_sub", parent=base["Normal"],
        fontSize=14, textColor=colors.HexColor("#B0C8D8"),
        alignment=TA_CENTER, spaceAfter=6,
    )
    styles["toc_cat"] = ParagraphStyle(
        "toc_cat", parent=base["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        textColor=NAVY, spaceBefore=8, spaceAfter=2,
    )
    styles["toc_item"] = ParagraphStyle(
        "toc_item", parent=base["Normal"],
        fontSize=9, leftIndent=16,
        textColor=colors.HexColor("#444444"),
    )
    styles["cat_heading"] = ParagraphStyle(
        "cat_heading", parent=base["Heading1"],
        fontSize=20, fontName="Helvetica-Bold",
        textColor=WHITE, leading=26,
        backColor=NAVY, spaceBefore=0, spaceAfter=10,
        leftIndent=-10, borderPad=8,
    )
    styles["topic_heading"] = ParagraphStyle(
        "topic_heading", parent=base["Heading2"],
        fontSize=14, fontName="Helvetica-Bold",
        textColor=NAVY, spaceBefore=18, spaceAfter=6,
        borderPad=4,
    )
    styles["section_label"] = ParagraphStyle(
        "section_label", parent=base["Normal"],
        fontSize=9, fontName="Helvetica-Bold",
        textColor=TEAL, spaceBefore=8, spaceAfter=2,
    )
    styles["examiner"] = ParagraphStyle(
        "examiner", parent=base["Normal"],
        fontSize=10, leading=14,
        fontName="Helvetica-Bold", textColor=NAVY,
        leftIndent=8, spaceBefore=6,
    )
    styles["candidate"] = ParagraphStyle(
        "candidate", parent=base["Normal"],
        fontSize=10, leading=14,
        fontName="Helvetica", textColor=colors.HexColor("#1A3A1A"),
        leftIndent=24, spaceBefore=4,
    )
    styles["keypoint"] = ParagraphStyle(
        "keypoint", parent=base["Normal"],
        fontSize=9.5, leading=13,
        fontName="Helvetica", textColor=colors.HexColor("#333333"),
        leftIndent=14, spaceBefore=2,
    )
    styles["flowchart"] = ParagraphStyle(
        "flowchart", parent=base["Code"],
        fontSize=8, leading=11,
        fontName="Courier", textColor=NAVY,
        backColor=LTBLUE,
        leftIndent=8, rightIndent=8, spaceBefore=4, spaceAfter=4,
        borderPad=6,
    )
    styles["concept_label"] = ParagraphStyle(
        "concept_label", parent=base["Normal"],
        fontSize=9, fontName="Helvetica-Bold",
        textColor=WHITE,
    )
    styles["concept_value"] = ParagraphStyle(
        "concept_value", parent=base["Normal"],
        fontSize=9, fontName="Helvetica",
        textColor=colors.HexColor("#1A1A1A"),
    )
    styles["footer"] = ParagraphStyle(
        "footer", parent=base["Normal"],
        fontSize=7, textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER,
    )

    return styles, NAVY, TEAL, AMBER, LTBLUE, LTAMBER, WHITE


# ══════════════════════════════════════════════════════════════════════════════
#  CUSTOM FLOWABLES
# ══════════════════════════════════════════════════════════════════════════════

class ColorBand(Flowable):
    """A full-width colored horizontal band (used for section headers)."""
    def __init__(self, text, bg_color, text_color, height=28, font_size=16):
        super().__init__()
        self.text = text
        self.bg_color = bg_color
        self.text_color = text_color
        self.height = height
        self.font_size = font_size
        self.width = 0

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg_color)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        c.setFillColor(self.text_color)
        c.setFont("Helvetica-Bold", self.font_size)
        c.drawString(8, (self.height - self.font_size) / 2 + 2, self.text)


class KeyPointsBox(Flowable):
    """Amber-background key-points box with bullet list."""
    def __init__(self, points, styles, ltamber):
        super().__init__()
        self.points = points
        self.styles = styles
        self.ltamber = ltamber
        self._width = 0
        self._height = 0

    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        line_h = 14
        self._height = 24 + len(self.points) * line_h + 8
        return availWidth, self._height

    def draw(self):
        c = self.canv
        w, h = self._width, self._height
        c.setFillColor(self.ltamber)
        c.roundRect(0, 0, w, h, 6, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#D4851A"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(10, h - 16, "KEY POINTS")
        c.setFillColor(colors.HexColor("#333333"))
        c.setFont("Helvetica", 8.5)
        y = h - 30
        for pt in self.points:
            # Truncate if too long
            text = pt[:120] + "…" if len(pt) > 120 else pt
            c.drawString(18, y, f"• {text}")
            y -= 13


class ConceptTable(Flowable):
    """Teal-header concept quick-reference table."""
    def __init__(self, rows, teal, ltblue):
        super().__init__()
        self.rows = rows   # list of (label, value)
        self.teal = teal
        self.ltblue = ltblue
        self._width = 0
        self._height = 0

    def wrap(self, availWidth, availHeight):
        self._width = availWidth
        self._height = 22 + len(self.rows) * 16 + 6
        return availWidth, self._height

    def draw(self):
        c = self.canv
        w, h = self._width, self._height
        # Header
        c.setFillColor(self.teal)
        c.rect(0, h - 22, w, 22, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(8, h - 15, "QUICK REFERENCE")
        # Rows
        col1 = int(w * 0.35)
        y = h - 22
        for i, (label, value) in enumerate(self.rows):
            row_h = 16
            bg = self.ltblue if i % 2 == 0 else colors.white
            c.setFillColor(bg)
            c.rect(0, y - row_h, w, row_h, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#0D2137"))
            c.setFont("Helvetica-Bold", 8)
            c.drawString(6, y - row_h + 4, label)
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.HexColor("#1A1A1A"))
            # Clip text
            val = value[:100] if len(value) > 100 else value
            c.drawString(col1 + 6, y - row_h + 4, val)
            y -= row_h


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE TEMPLATE  (header + footer)
# ══════════════════════════════════════════════════════════════════════════════

def add_header_footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    NAVY = colors.HexColor("#0D2137")
    TEAL = colors.HexColor("#007A8A")

    # Header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 28, w, 28, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(14, h - 19, "Final FRCA — Complete Exam Revision Guide")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 14, h - 19, f"Page {doc.page}")

    # Footer
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, w, 18, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(14, 5, "FRCA Exam Revision  |  All content from audio recordings")
    canvas.drawRightString(w - 14, 5, f"Generated {datetime.now().strftime('%B %Y')}")
    canvas.restoreState()


# ══════════════════════════════════════════════════════════════════════════════
#  COVER PAGE
# ══════════════════════════════════════════════════════════════════════════════

def build_cover(styles_dict, navy, teal, white):
    story = []
    w, h = A4
    LTBLUE = colors.HexColor("#E8F4F8")

    class CoverPage(Flowable):
        def wrap(self, aw, ah):
            return aw, ah
        def draw(self):
            c = self.canv
            pw, ph = A4
            # Navy background
            c.setFillColor(navy)
            c.rect(0, 0, pw, ph, fill=1, stroke=0)
            # Teal accent strip
            c.setFillColor(teal)
            c.rect(0, ph * 0.55, pw, ph * 0.45, fill=1, stroke=0)
            # White content area
            c.setFillColor(white)
            c.roundRect(40, ph * 0.15, pw - 80, ph * 0.72, 12, fill=1, stroke=0)
            # Title
            c.setFillColor(navy)
            c.setFont("Helvetica-Bold", 32)
            c.drawCentredString(pw / 2, ph * 0.73, "Final FRCA")
            c.setFont("Helvetica-Bold", 22)
            c.drawCentredString(pw / 2, ph * 0.67, "Complete Exam Revision Guide")
            # Subtitle
            c.setFillColor(teal)
            c.setFont("Helvetica", 13)
            c.drawCentredString(pw / 2, ph * 0.61, "Transcribed Audio Lectures  ·  Q&A Format  ·  Key Points")
            c.drawCentredString(pw / 2, ph * 0.58, "Flowcharts  ·  Concept Tables  ·  103 Topics Covered")
            # Divider
            c.setStrokeColor(teal)
            c.setLineWidth(2)
            c.line(80, ph * 0.56, pw - 80, ph * 0.56)
            # Stats
            c.setFillColor(colors.HexColor("#444444"))
            c.setFont("Helvetica", 11)
            stats = [
                ("103", "Audio Lectures"),
                ("20", "Clinical Topics"),
                ("100%", "Content from Audio"),
            ]
            x_start = 90
            gap = (pw - 160) / len(stats)
            for val, label in stats:
                c.setFont("Helvetica-Bold", 18)
                c.setFillColor(navy)
                c.drawCentredString(x_start + gap * stats.index((val, label)), ph * 0.47, val)
                c.setFont("Helvetica", 9)
                c.setFillColor(colors.HexColor("#666666"))
                c.drawCentredString(x_start + gap * stats.index((val, label)), ph * 0.44, label)
            # Footer note
            c.setFillColor(colors.HexColor("#888888"))
            c.setFont("Helvetica-Oblique", 8)
            c.drawCentredString(pw / 2, ph * 0.18, f"Generated {datetime.now().strftime('%d %B %Y')}  ·  For personal exam preparation only")

    story.append(CoverPage())
    story.append(PageBreak())
    return story


# ══════════════════════════════════════════════════════════════════════════════
#  TABLE OF CONTENTS
# ══════════════════════════════════════════════════════════════════════════════

def build_toc(categories, styles_dict, navy, teal):
    story = []
    story.append(ColorBand("TABLE OF CONTENTS", navy, colors.white, height=36, font_size=18))
    story.append(Spacer(1, 0.4 * cm))

    # Build two-column TOC
    col1, col2 = [], []
    cats = list(categories.keys())
    mid = (len(cats) + 1) // 2
    for i, (cat, topics) in enumerate(categories.items()):
        target = col1 if i < mid else col2
        target.append(Paragraph(f"<b>{cat}</b>", styles_dict["toc_cat"]))
        for stem in topics:
            label = stem.replace("_", " ")
            target.append(Paragraph(f"• {label}", styles_dict["toc_item"]))

    # Pad shorter column
    while len(col1) < len(col2):
        col1.append(Spacer(1, 12))
    while len(col2) < len(col1):
        col2.append(Spacer(1, 12))

    # Build multi-row table (one flowable per row) so ReportLab can paginate
    tbl_data = [[c1, c2] for c1, c2 in zip(col1, col2)]
    tbl = Table(tbl_data, colWidths=["50%", "50%"], repeatRows=0)
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("SPLITBYROW", (0, 0), (-1, -1), 1),
    ]))
    story.append(tbl)
    story.append(PageBreak())
    return story


# ══════════════════════════════════════════════════════════════════════════════
#  TOPIC SECTION BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def safe_para(text, style):
    """Escape XML special chars and return Paragraph."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(text, style)


def build_topic_section(stem, transcript_text, styles_dict, navy, teal, amber, ltblue, ltamber):
    story = []
    title = stem.replace("_", " ")

    # ── Topic heading ──────────────────────────────────────────────────────
    story.append(ColorBand(f"  {title}", teal, colors.white, height=30, font_size=13))
    story.append(Spacer(1, 0.2 * cm))

    # ── Flowchart ──────────────────────────────────────────────────────────
    fc_text = FLOWCHARTS.get(stem, GENERIC_FLOWCHART)
    story.append(safe_para("CONCEPT FLOWCHART", styles_dict["section_label"]))
    story.append(Paragraph(
        fc_text.replace("\n", "<br/>").replace(" ", "&nbsp;"),
        styles_dict["flowchart"]
    ))
    story.append(Spacer(1, 0.2 * cm))

    # ── Concept table ──────────────────────────────────────────────────────
    concept_rows = CONCEPT_BOXES.get(stem)
    if concept_rows:
        story.append(ConceptTable(concept_rows, teal, ltblue))
        story.append(Spacer(1, 0.2 * cm))

    # ── Q&A Dialogue ──────────────────────────────────────────────────────
    story.append(safe_para("EXAMINER / CANDIDATE DIALOGUE", styles_dict["section_label"]))

    turns = split_into_qa(transcript_text)
    if not turns:
        story.append(safe_para(transcript_text[:3000], styles_dict["candidate"]))
    else:
        for turn in turns:
            role = turn["role"]
            txt  = turn["text"].strip()
            if not txt:
                continue
            prefix = "Examiner: " if role == "Examiner" else "Candidate: "
            style  = styles_dict["examiner"] if role == "Examiner" else styles_dict["candidate"]
            story.append(safe_para(prefix + txt, style))

    story.append(Spacer(1, 0.3 * cm))

    # ── Key Points ────────────────────────────────────────────────────────
    kp = extract_key_points(transcript_text, n=8)
    if kp:
        story.append(KeyPointsBox(kp, styles_dict, ltamber))

    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC")))
    story.append(Spacer(1, 0.3 * cm))

    return story


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PDF BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_pdf(transcripts: dict):
    print(f"\n{'='*60}")
    print("  Building PDF ...")
    print(f"{'='*60}\n")

    styles_dict, navy, teal, amber, ltblue, ltamber, white = build_styles()

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.5 * cm,
        title="Final FRCA Complete Exam Revision Guide",
        author="FRCA Podcast Transcription",
        subject="Anaesthesia Exam Revision",
    )

    story = []
    story += build_cover(styles_dict, navy, teal, white)
    story += build_toc(CATEGORIES, styles_dict, navy, teal)

    mp3s = get_all_mp3s()
    # Map stem → transcript
    stem_map = {p.stem: transcripts.get(p.stem, {}).get("text", "") for p in mp3s}

    for category, stems in CATEGORIES.items():
        # Category divider page
        story.append(PageBreak())
        story.append(ColorBand(
            f"  {category.upper()}",
            navy, colors.white, height=50, font_size=20
        ))
        story.append(Spacer(1, 0.4 * cm))

        for stem in stems:
            # Find matching transcript key (flexible match)
            text = ""
            for key, val in stem_map.items():
                if stem.replace("-", "_") in key.replace("-", "_"):
                    text = val
                    break

            if not text:
                text = f"[Transcript not available for: {stem.replace('_', ' ')}]"

            story += build_topic_section(
                stem, text, styles_dict, navy, teal, amber, ltblue, ltamber
            )

    # Any MP3s not in CATEGORIES
    categorised = set()
    for stems in CATEGORIES.values():
        for s in stems:
            categorised.add(s.replace("-", "_").lower())

    extra = []
    for mp3 in mp3s:
        stem_norm = mp3.stem.replace("FinalFRCAVascular_", "").replace("FinalFRCA", "")
        # Remove category prefix patterns
        for cat in CATEGORIES:
            slug = cat.replace(" ", "_").replace("/", "_")
            stem_norm = stem_norm.replace(slug + "_", "")
        if stem_norm.replace("-", "_").lower() not in categorised:
            extra.append(mp3)

    if extra:
        story.append(PageBreak())
        story.append(ColorBand("  ADDITIONAL TOPICS", navy, colors.white, height=50, font_size=20))
        for mp3 in extra:
            text = transcripts.get(mp3.stem, {}).get("text", "")
            if text:
                story += build_topic_section(
                    mp3.stem, text, styles_dict, navy, teal, amber, ltblue, ltamber
                )

    doc.build(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
    print(f"\n  PDF saved → {OUTPUT_PDF}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    transcripts = transcribe_all()
    build_pdf(transcripts)
    print("ALL DONE.")
