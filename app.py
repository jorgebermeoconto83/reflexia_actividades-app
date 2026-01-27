import base64
import os

import streamlit as st
from openai import OpenAI

# -----------------------
# Config UI
# -----------------------
st.set_page_config(page_title="ReflexIA (v3) — Actividades", page_icon="✅", layout="centered")
st.title("ReflexIA (v3) — Evaluador de Actividades")
st.caption("Evalúa coherencia entre el nivel Bloom declarado y la actividad (texto o imagen).")

# -----------------------
# OpenAI key (Streamlit Secrets primero)
# -----------------------
def get_api_key() -> str | None:
    # Streamlit Cloud: Settings -> Secrets (recomendado)
    if "OPENAI_API_KEY" in st.secrets:
        return st.secrets["OPENAI_API_KEY"]
    # Fallback local (solo desarrollo)
    return os.getenv("OPENAI_API_KEY")

api_key = get_api_key()
if not api_key:
    st.error(
        "Falta configurar OPENAI_API_KEY.\n\n"
        "En Streamlit Cloud: Settings → Secrets → agrega:\n"
        "OPENAI_API_KEY = \"tu_clave\""
    )
    st.stop()

client = OpenAI(api_key=api_key)

# -----------------------
# ReflexIA v3 (con parche Bloom)
# -----------------------
REFLEXIA_V3 = r"""
Rol
Eres ReflexIA, revisor crítico pedagógico.
Tu tarea es evaluar actividades formativas contrastándolas únicamente con el nivel cognitivo declarado en el objetivo de aprendizaje.

No decides a qué nivel “debería” llegar la actividad.
No propongas un nivel diferente al que declara el docente.

Entrada esperada
1) Objetivo de aprendizaje
2) Actividad (texto / imagen legible / URL pública accesible sin login)

Regla crítica
Si ReflexIA no puede leer ni acceder a la actividad real, NO evalúes ni supongas nada.
Debes: indicar que no es evaluable, describir qué insumo falta, y detener la evaluación.

Regla adicional (declaración explícita del nivel Bloom)
Si el objetivo incluye una línea con el formato:
"Nivel Bloom declarado por el docente: <X>"
entonces <X> es el nivel oficial a usar en toda la evaluación, incluso si el verbo del objetivo es ambiguo o no coincide.
No infieras ni sugieras otros niveles.

Procedimiento
Paso 0 — Verificación de acceso: si no puedes leer el contenido, detén la evaluación.
Paso 1 — Nivel cognitivo declarado: usa el nivel Bloom declarado explícitamente si está presente. Si no, identifica el nivel cognitivo explícito en el objetivo. No infieras intención.
Paso 2 — Proceso cognitivo activado: analiza qué proceso activa realmente la actividad observable.
Paso 3 — Evaluación de coherencia: emite un solo juicio: Coherente / Parcialmente coherente / No coherente.
Paso 4 — Fundamentación breve: máximo 3 puntos observables. Sin textos largos.
Paso 5 — Pregunta de mejora: no propongas otro nivel. Pregunta al docente cómo desea mejorar con alternativas.

Formato de salida
Si no evaluable:
Estado: No evaluable
Motivo: (frase directa)
Insumo requerido: (texto / captura específica)

Si evaluable:
1. Nivel cognitivo declarado en el objetivo:
2. Proceso cognitivo activado por la actividad:
3. Juicio de coherencia:
4. Fundamentación (máx. 3 puntos):
5. Pregunta de mejora al docente (con alternativas):

Estilo
Directo, preciso, sin ambigüedades, sin textos largos.
"""

# -----------------------
# Prompt de seguimiento (decisión del docente)
# -----------------------
REFLEXIA_FOLLOWUP = r"""
Eres ReflexIA. Vas a proponer un siguiente paso a partir de:
- Nivel Bloom declarado por el docente (NO lo cambies salvo que el docente lo pida explícitamente).
- Objetivo (texto) del docente
- Resultado previo de evaluación
- Decisión elegida por el docente

Reglas:
- No seas largo. Máximo 6 bullets.
- Da opciones accionables (consignas ejemplo, criterios, retroalimentación).
- Si el docente pide subir/bajar nivel, entonces sí: propone cómo reestructurar la misma actividad para ese nuevo nivel.
"""


# -----------------------
# Helpers
# -----------------------
def to_data_url(uploaded_file) -> str:
    raw = uploaded_file.getvalue()
    b64 = base64.b64encode(raw).decode("utf-8")
    mime = uploaded_file.type or "image/png"
    return f"data:{mime};base64,{b64}"

def run_reflexia_text(model: str, objetivo: str, actividad: str) -> str:
    resp = client.responses.create(
        model=model,
        instructions=REFLEXIA_V3,
        input=f"{objetivo}\n\nActividad (texto):\n{actividad}",
    )
    return resp.output_text

def run_reflexia_image(model: str, objetivo: str, image_data_url: str) -> str:
    resp = client.responses.create(
        model=model,
        instructions=REFLEXIA_V3,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"{objetivo}\n\nActividad: (imagen adjunta)"},
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
    )
    return resp.output_text

# -----------------------
# Form
# -----------------------
# ---- Selección de modo FUERA del form ----
modo = st.radio("Entrada de actividad", ["Texto", "Imagen"], horizontal=True)

with st.form("reflexia_form"):
    col1, col2 = st.columns([1, 1])

    with col1:
        bloom = st.selectbox(
            "Nivel Bloom (obligatorio)",
            ["Recordar", "Comprender", "Aplicar", "Analizar", "Evaluar", "Crear"],
            index=2,
        )

    with col2:
       model = "gpt-4o-mini"

    objetivo_texto = st.text_area(
        "Objetivo de aprendizaje (texto)",
        placeholder="Ej.: Usar el pasado simple para describir acciones de la semana pasada.",
        height=90,
    )

    # --- Entrada dinámica ---
    if modo == "Texto":
        actividad_texto = st.text_area(
            "Actividad (texto)",
            placeholder="Pega la consigna y describe qué hace el estudiante.",
            height=160,
        )
        imagen = None
    else:
        imagen = st.file_uploader(
            "Actividad (imagen)",
            type=["png", "jpg", "jpeg"]
        )
        actividad_texto = None

    submit = st.form_submit_button("Evaluar")

if submit:
    if not objetivo_texto.strip():
        st.error("Falta el objetivo (texto).")
        st.stop()

    objetivo = f"Nivel Bloom declarado por el docente: {bloom}\nObjetivo de aprendizaje (texto): {objetivo_texto.strip()}"

    with st.spinner("Evaluando con ReflexIA…"):
        try:
            if modo == "Texto":
                if not actividad_texto or not actividad_texto.strip():
                    st.error("Falta la actividad en texto.")
                    st.stop()
                out = run_reflexia_text(model, objetivo, actividad_texto.strip())
            else:
                if not imagen:
                    st.error("No subiste ninguna imagen.")
                    st.stop()
                out = run_reflexia_image(model, objetivo, to_data_url(imagen))

            st.subheader("Resultado")
            st.code(out, language="text")
# ---- Guardar contexto para decisiones posteriores ----
            st.session_state["reflexia_ready"] = True
            st.session_state["reflexia_result"] = out
            st.session_state["reflexia_objetivo"] = objetivo
            st.session_state["reflexia_bloom"] = bloom
            st.session_state["reflexia_modo"] = modo
            st.session_state["reflexia_model"] = model


        except Exception as e:
            st.error(f"Error al llamar a la API: {e}")
            st.stop()

# -----------------------
# Decisión del docente (UI)
# -----------------------
if st.session_state.get("reflexia_ready"):
    st.subheader("Decisión del docente")

    decision = st.selectbox(
        "¿Qué quieres hacer ahora?",
        [
            "Elegir 2 mejoras concretas manteniendo el nivel",
            "Pedir 3 alternativas lúdicas manteniendo el nivel",
            "Crear una rúbrica breve (3 criterios)",
            "Redactar retroalimentación automática (1–2 líneas)",
            "Subir el nivel (decisión del docente)",
            "Bajar el nivel (decisión del docente)",
        ],
        index=0
    )

    nuevo_nivel = None
    if "Subir el nivel" in decision or "Bajar el nivel" in decision:
        nuevo_nivel = st.selectbox(
            "Nuevo nivel Bloom (decisión del docente):",
            ["Recordar", "Comprender", "Aplicar", "Analizar", "Evaluar", "Crear"],
            index=["Recordar","Comprender","Aplicar","Analizar","Evaluar","Crear"].index(
                st.session_state["reflexia_bloom"]
            ),
        )

    # Botón (aún no ejecuta IA; solo prepara el siguiente paso)
    if st.button("Aplicar decisión"):
    follow_input = f"""
Nivel Bloom declarado por el docente: {st.session_state["reflexia_bloom"]}

Objetivo de aprendizaje (texto):
{st.session_state["reflexia_objetivo"].split('Objetivo de aprendizaje (texto):',1)[-1].strip()}

Resultado previo de ReflexIA:
{st.session_state["reflexia_result"]}

Decisión del docente:
{decision}
"""

    if nuevo_nivel:
        follow_input += f"\nNuevo nivel Bloom decidido por el docente: {nuevo_nivel}\n"

    with st.spinner("Generando siguiente paso…"):
        try:
            resp2 = client.responses.create(
                model=st.session_state["reflexia_model"],
                instructions=REFLEXIA_FOLLOWUP,
                input=follow_input
            )
            st.subheader("Siguiente paso sugerido")
            st.code(resp2.output_text, language="text")
        except Exception as e:
            st.error(f"Error al generar el siguiente paso: {e}")



st.divider()
st.caption(
    "Implementación con Responses API (recomendada para proyectos nuevos)."
)





