import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

import agent

# --- Paths ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SAKER_DIR = BASE_DIR / "saker"
DATA_DIR.mkdir(exist_ok=True)
CORRECTIONS_FILE = DATA_DIR / "corrections.json"

# --- Page config ---
st.set_page_config(page_title="Aggrator – Artikkelassistent", layout="centered")

st.markdown("""
<style>
    .stApp { max-width: 780px; margin: 0 auto; }
    h1 { color: #1b4332; }
    .step-done { color: #40916c; font-size: 12px; text-align: center; }
    .step-active { color: #1b4332; font-weight: bold; font-size: 13px; text-align: center; }
    .step-inactive { color: #aaa; font-size: 12px; text-align: center; }
    .step-disabled { color: #ddd; font-size: 12px; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- News type definitions ---
NEWS_TYPES = {
    "type_b": "B – Ny-partner (selskap inn i Aggrator)",
    "type_a": "A – Nyhetsmelding (kunngjøring, tilskudd, samarbeidsavtale)",
    "type_c": "C – Program / arrangement-rapport",
    "type_d": "D – Analytisk artikkel (trender, bransje, ressurs, politikk)",
    "annet":  "Annet",
}

# --- State init ---
DEFAULTS = {
    "stage": "input",
    "news_type": "",
    "responsible": "",
    "uploaded_files": [],
    "draft": "",
    "vilde_edit": "",
    "company_edit": "",
    # Selskapsnyhet
    "company_name": "",
    "kam": "",
    "founder": "",
    "description": "",
    # Aggrator-nyhet
    "aggrator_what": "",
    "aggrator_who": "",
    # Bransje / Ressurs
    "topic": "",
    "key_points": "",
    # Politikk
    "policy_what": "",
    "policy_relevance": "",
    # Felles
    "notes": "",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- API key check ---
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error("**ANTHROPIC_API_KEY mangler.** Start appen med: `ANTHROPIC_API_KEY=sk-... streamlit run app.py`")
    st.stop()

# --- Helpers ---
def load_corrections() -> dict:
    if CORRECTIONS_FILE.exists():
        return json.loads(CORRECTIONS_FILE.read_text())
    return {"corrections": [], "lessons": []}

def save_correction(source: str, before: str, after: str) -> None:
    data = load_corrections()
    data.setdefault("corrections", []).append({
        "source": source,
        "before": before[:3000],
        "after": after[:3000],
        "ts": datetime.now().isoformat(),
    })
    data["corrections"] = data["corrections"][-20:]
    CORRECTIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def reset_session() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]

def is_incubator_article() -> bool:
    return st.session_state.news_type == "type_b"

# --- Progress bar ---
STAGE_ORDER = ["input", "draft", "vilde_review", "company_review", "done"]
STAGE_LABELS = ["Inndata", "Utkast", "Vilde", "Selskap", "Ferdig"]

def show_progress() -> None:
    current_idx = STAGE_ORDER.index(st.session_state.stage) if st.session_state.stage in STAGE_ORDER else 0
    cols = st.columns(len(STAGE_LABELS))
    for i, (col, label) in enumerate(zip(cols, STAGE_LABELS)):
        if i == 3 and not is_incubator_article():
            col.markdown(f"<p class='step-disabled'>{label}</p>", unsafe_allow_html=True)
        elif i < current_idx:
            col.markdown(f"<p class='step-done'>✓ {label}</p>", unsafe_allow_html=True)
        elif i == current_idx:
            col.markdown(f"<p class='step-active'>{label}</p>", unsafe_allow_html=True)
        else:
            col.markdown(f"<p class='step-inactive'>{label}</p>", unsafe_allow_html=True)
    st.divider()

show_progress()


# ─── STAGE: input ─────────────────────────────────────────────────────────────

if st.session_state.stage == "input":
    st.title("Ny artikkel")

    st.selectbox(
        "Hva slags nyhet er dette?",
        options=[""] + list(NEWS_TYPES.keys()),
        format_func=lambda k: "Velg type ..." if k == "" else NEWS_TYPES[k],
        key="news_type",
    )

    news = st.session_state.news_type
    ready = False

    if news == "type_b":
        st.divider()
        st.text_input("Selskapsnavn *", key="company_name")
        st.text_input(
            "Gründer / daglig leder *",
            key="founder",
            placeholder="Fornavn Etternavn, Tittel – flere: Navn 1, CEO / Navn 2, CTO",
        )
        st.text_area("Hva driver selskapet med? *", key="description", height=100)
        st.text_area("Ekstra notater", key="notes", height=90,
            placeholder="Investeringsbeløp, partnere, milepæler, sitater, lenker ...")
        ready = bool(
            st.session_state.company_name.strip()
            and st.session_state.founder.strip()
            and st.session_state.description.strip()
        )

    elif news == "type_a":
        st.divider()
        st.text_area("Hva handler nyheten om? *", key="aggrator_what", height=110,
            placeholder="Ny ansatt, tilskudd, samarbeidsavtale, milepæl ...")
        st.text_input("Hvem er involvert? (navn og rolle)", key="aggrator_who")
        st.text_area("Ekstra notater", key="notes", height=90)
        ready = bool(st.session_state.aggrator_what.strip())

    elif news == "type_c":
        st.divider()
        st.text_input("Program / arrangement *", key="topic",
            placeholder="F.eks. AgriScale Spain 2026 ...")
        st.text_area("Hva skjedde? *", key="key_points", height=130,
            placeholder="Beskriv per dag eller fase – hvem møtte dere, hva ble resultatet ...")
        st.text_area("Ekstra notater", key="notes", height=90)
        ready = bool(st.session_state.topic.strip() and st.session_state.key_points.strip())

    elif news == "type_d":
        st.divider()
        st.text_input("Tema / tittel *", key="topic",
            placeholder="F.eks. «Fem trender som former landbruket nå» ...")
        st.text_area("Nøkkelpunkter *", key="key_points", height=130,
            placeholder="Trender, argumenter, eksempler, kilder ...")
        st.text_area("Ekstra notater", key="notes", height=90)
        ready = bool(st.session_state.topic.strip() and st.session_state.key_points.strip())

    elif news == "annet":
        st.divider()
        st.text_area("Beskriv hva artikkelen handler om *", key="notes", height=160,
            placeholder="Skriv fritt – jo mer kontekst du gir, jo bedre blir artikkelen ...")
        ready = bool(st.session_state.notes.strip())

    if news:
        st.divider()
        file_label = (
            "Filer fra selskapet (pitch deck, pressemelding ...)"
            if news == "selskapsnyhet"
            else "Kontekstfiler (rapport, pressemelding, bakgrunnsnotat ...)"
        )
        uploaded = st.file_uploader(
            file_label,
            type=["pdf", "pptx", "docx", "txt"],
            accept_multiple_files=True,
        )
        responsible_label = (
            "Ansvarlig for selskapet hos Aggrator *"
            if news == "selskapsnyhet"
            else "Ditt navn *"
        )
        st.text_input(responsible_label, key="responsible")

        st.divider()
        if st.button("Generer artikkel →", type="primary", disabled=not (ready and st.session_state.responsible.strip())):
            st.session_state.uploaded_files = [
                {"name": f.name, "bytes": f.read()} for f in (uploaded or [])
            ]
            fields = {
                "company_name":  st.session_state.company_name,
                "founder":       st.session_state.founder,
                "description":   st.session_state.description,
                "aggrator_what": st.session_state.aggrator_what,
                "aggrator_who":  st.session_state.aggrator_who,
                "topic":         st.session_state.topic,
                "key_points":    st.session_state.key_points,
                "notes":         st.session_state.notes,
                "responsible":   st.session_state.responsible,
            }
            with st.spinner("Skriver artikkel..."):
                draft = agent.generate_article(
                    news_type=news,
                    fields=fields,
                    corrections=load_corrections(),
                    files_data=st.session_state.uploaded_files,
                )
            st.session_state.draft = draft
            st.session_state.vilde_edit = draft
            st.session_state.stage = "draft"
            st.rerun()


# ─── STAGE: draft ─────────────────────────────────────────────────────────────

elif st.session_state.stage == "draft":
    st.title("Artikkelutkast")

    tab1, tab2 = st.tabs(["Forhåndsvisning", "Markdown"])
    with tab1:
        st.markdown(st.session_state.draft)
    with tab2:
        st.code(st.session_state.draft, language="markdown")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Tilbake"):
            st.session_state.stage = "input"
            st.rerun()
    with col2:
        if st.button("Send til korrektur hos Vilde →", type="primary"):
            if "vilde_textarea" in st.session_state:
                del st.session_state["vilde_textarea"]
            st.session_state.stage = "vilde_review"
            st.rerun()


# ─── STAGE: vilde_review ──────────────────────────────────────────────────────

elif st.session_state.stage == "vilde_review":
    st.title("Korrektur – kommunikasjonssjef")
    st.caption("Les artikkelen og gjør endringer direkte i tekstfeltet.")

    if "vilde_textarea" not in st.session_state:
        st.session_state["vilde_textarea"] = st.session_state.vilde_edit

    tab1, tab2 = st.tabs(["Rediger", "Forhåndsvisning"])
    with tab1:
        st.text_area("Artikkel", key="vilde_textarea", height=520, label_visibility="collapsed")
    with tab2:
        st.markdown(st.session_state.get("vilde_textarea", st.session_state.vilde_edit))

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Tilbake"):
            st.session_state.stage = "draft"
            st.rerun()
    with col2:
        if st.button("Godkjenn →", type="primary"):
            edited = st.session_state.get("vilde_textarea", st.session_state.vilde_edit)
            st.session_state.vilde_edit = edited
            st.session_state.company_edit = edited

            if edited.strip() != st.session_state.draft.strip():
                save_correction("vilde", st.session_state.draft, edited)
                with st.spinner("Lagrer stilkorrigeringer..."):
                    agent.extract_lesson(st.session_state.draft, edited, CORRECTIONS_FILE)

            if is_incubator_article() and st.session_state.company_name.strip():
                if "company_textarea" in st.session_state:
                    del st.session_state["company_textarea"]
                st.session_state.stage = "company_review"
            else:
                st.session_state.stage = "done"
            st.rerun()


# ─── STAGE: company_review ────────────────────────────────────────────────────

elif st.session_state.stage == "company_review":
    company = st.session_state.company_name or "Selskapet"
    st.title(f"Korrektur – {company}")
    st.caption("Gjør korrigeringer på vegne av selskapet.")

    if "company_textarea" not in st.session_state:
        st.session_state["company_textarea"] = st.session_state.company_edit

    tab1, tab2 = st.tabs(["Rediger", "Forhåndsvisning"])
    with tab1:
        st.text_area("Artikkel", key="company_textarea", height=520, label_visibility="collapsed")
    with tab2:
        st.markdown(st.session_state.get("company_textarea", st.session_state.company_edit))

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Tilbake"):
            st.session_state.stage = "vilde_review"
            st.rerun()
    with col2:
        if st.button("Godkjenn og avslutt →", type="primary"):
            edited = st.session_state.get("company_textarea", st.session_state.company_edit)
            st.session_state.company_edit = edited

            if edited.strip() != st.session_state.vilde_edit.strip():
                save_correction(company, st.session_state.vilde_edit, edited)
                with st.spinner(f"Oppdaterer profil for {company}..."):
                    agent.update_company_profile(
                        company,
                        st.session_state.vilde_edit,
                        edited,
                        SAKER_DIR,
                    )

            st.session_state.stage = "done"
            st.rerun()


# ─── STAGE: done ──────────────────────────────────────────────────────────────

elif st.session_state.stage == "done":
    st.success("Artikkelen er godkjent og klar for publisering!")

    final = (
        st.session_state.company_edit
        or st.session_state.vilde_edit
        or st.session_state.draft
    )

    corrections_data = load_corrections()
    lessons = corrections_data.get("lessons", [])
    if lessons:
        with st.expander(f"Agenten har lært {len(lessons)} stilregel(er) totalt"):
            for l in lessons[-10:]:
                st.markdown(f"- {l['lesson']} *({l.get('ts', '')[:10]})*")

    tab1, tab2 = st.tabs(["Forhåndsvisning", "Markdown"])
    with tab1:
        st.markdown(final)
    with tab2:
        st.code(final, language="markdown")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Last ned .md",
            data=final,
            file_name=f"artikkel-{datetime.now().strftime('%Y%m%d-%H%M')}.md",
            mime="text/markdown",
        )
    with col2:
        if st.button("Skriv ny artikkel", type="primary"):
            reset_session()
            st.rerun()
