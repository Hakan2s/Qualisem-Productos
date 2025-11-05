"""
Qualisem Productos — Control de Almacén de Fitosanitarios (Streamlit + SQLite)
Autor: ChatGPT (GPT-5 Thinking)
Fecha: 2025-11-04

README rápido
-------------
- Este app gestiona **compras/ingresos** al almacén, **consumo/uso** en campo, **inventario**, **historial** y **cuentas por pagar**.
- Productos: nombre, ingrediente activo, categoría, peligrosidad (rojo/amarillo/azul/verde), unidad, empresa (proveedor habitual) y **stock mínimo** (para alertas).
- Ingresos (compras): empresa, estado de pago (pagado/debe), **costo unitario** (opcional) y cantidad.
- Consumo (uso): cantidad, destino/actividad, notas.
- Reportes: resumen por categoría, filtros avanzados y cuentas por pagar por empresa.

Instalación
-----------
1) Archivos: `app.py`, `requirements.txt`, carpeta `data/` vacía.
2) `pip install -r requirements.txt`
3) `streamlit run app.py`

requirements.txt sugerido:
streamlit>=1.37
pandas>=2.2
"""

from __future__ import annotations
import os
import sqlite3
from datetime import datetime, date
from typing import Literal, Dict

import pandas as pd
import streamlit as st

# =============== Config básica ===============
st.set_page_config(page_title="Qualisem Productos | Almacén", page_icon="🌿", layout="wide")

DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "fitosanitarios.db")
EXPORT_DIR = DB_DIR

HAZARD_LEVELS: Dict[str, str] = {
    "rojo": "🟥 Rojo (Alto)",
    "amarillo": "🟨 Amarillo (Moderado)",
    "azul": "🟦 Azul (Cuidado)",
    "verde": "🟩 Verde (Bajo)",
}
HAZARD_KEYS = list(HAZARD_LEVELS.keys())

# =============== Inicialización BD ===============

def init_storage():
    os.makedirs(DB_DIR, exist_ok=True)


def get_conn():
    init_storage()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ingrediente_activo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            peligrosidad TEXT NOT NULL CHECK (peligrosidad IN ('rojo','amarillo','azul','verde')),
            unidad TEXT NOT NULL DEFAULT 'L',
            empresa TEXT,
            stock_minimo REAL NOT NULL DEFAULT 0,
            stock REAL NOT NULL DEFAULT 0
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('ingreso','consumo','ajuste')),
            cantidad REAL NOT NULL,
            usuario TEXT,
            notas TEXT,
            empresa TEXT,
            estado_pago TEXT CHECK (estado_pago IN ('pagado','debe')),
            costo_unitario REAL,
            destino TEXT,
            FOREIGN KEY(producto_id) REFERENCES productos(id) ON DELETE CASCADE
        );
        """
    )

    conn.commit()
    conn.close()


def migrate_db():
    """Ajusta columnas para versiones anteriores."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(productos);")
    pcols = {r[1] for r in cur.fetchall()}
    if "empresa" not in pcols:
        cur.execute("ALTER TABLE productos ADD COLUMN empresa TEXT;")
    if "stock_minimo" not in pcols:
        cur.execute("ALTER TABLE productos ADD COLUMN stock_minimo REAL NOT NULL DEFAULT 0;")

    cur.execute("PRAGMA table_info(movimientos);")
    mcols = {r[1] for r in cur.fetchall()}
    if "empresa" not in mcols:
        cur.execute("ALTER TABLE movimientos ADD COLUMN empresa TEXT;")
    if "estado_pago" not in mcols:
        cur.execute("ALTER TABLE movimientos ADD COLUMN estado_pago TEXT;")
    if "costo_unitario" not in mcols:
        cur.execute("ALTER TABLE movimientos ADD COLUMN costo_unitario REAL;")
    if "destino" not in mcols:
        cur.execute("ALTER TABLE movimientos ADD COLUMN destino TEXT;")
    if "tipo" in mcols:
        # normalizar valores antiguos 'entrada'->'ingreso' y 'salida'->'consumo'
        cur.execute("UPDATE movimientos SET tipo='ingreso' WHERE tipo='entrada';")
        cur.execute("UPDATE movimientos SET tipo='consumo' WHERE tipo='salida';")

    conn.commit()
    conn.close()


init_db()
migrate_db()

# =============== DAO ===============

def add_producto(nombre: str, ingrediente_activo: str, categoria: str, peligrosidad: str, unidad: str = "L", empresa: str | None = None, stock_minimo: float = 0.0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO productos (nombre, ingrediente_activo, categoria, peligrosidad, unidad, empresa, stock_minimo, stock)
        VALUES (?,?,?,?,?,?,?,0)
        """,
        (nombre.strip(), ingrediente_activo.strip(), categoria.strip(), peligrosidad, unidad, (empresa.strip() if empresa else None), float(stock_minimo)),
    )
    conn.commit()
    conn.close()


def list_productos_df() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT id, nombre, ingrediente_activo, categoria, peligrosidad, unidad, empresa, stock_minimo, stock FROM productos ORDER BY nombre ASC",
        conn,
    )
    conn.close()
    return df


def get_producto(producto_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nombre, ingrediente_activo, categoria, peligrosidad, unidad, empresa, stock_minimo, stock FROM productos WHERE id=?",
        (producto_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        keys = ["id","nombre","ingrediente_activo","categoria","peligrosidad","unidad","empresa","stock_minimo","stock"]
        return dict(zip(keys, row))
    return None


def update_producto(producto_id: int, nombre: str, ingrediente_activo: str, categoria: str, peligrosidad: str, unidad: str, empresa: str | None, stock_minimo: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE productos
        SET nombre=?, ingrediente_activo=?, categoria=?, peligrosidad=?, unidad=?, empresa=?, stock_minimo=?
        WHERE id=?
        """,
        (nombre.strip(), ingrediente_activo.strip(), categoria.strip(), peligrosidad, unidad, (empresa.strip() if empresa else None), float(stock_minimo), producto_id),
    )
    conn.commit()
    conn.close()


def delete_producto(producto_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM productos WHERE id=?", (producto_id,))
    conn.commit()
    conn.close()


def registrar_movimiento(
    producto_id: int,
    tipo: Literal['ingreso','consumo','ajuste'],
    cantidad: float,
    usuario: str | None,
    notas: str | None,
    fecha_str: str,
    empresa: str | None = None,
    estado_pago: Literal['pagado','debe'] | None = None,
    costo_unitario: float | None = None,
    destino: str | None = None,
):
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a 0")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT stock FROM productos WHERE id=?", (producto_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError("Producto no encontrado")

    stock_actual = float(row[0])
    if tipo == 'ingreso':
        nuevo_stock = stock_actual + cantidad
    elif tipo == 'consumo':
        nuevo_stock = stock_actual - cantidad
        if nuevo_stock < 0:
            conn.close()
            raise ValueError("Stock insuficiente para registrar el consumo")
    else:  # ajuste libre
        nuevo_stock = cantidad  # se interpreta como stock final (si prefieres delta, cambia esta lógica)

    sql_ins = (
        "INSERT INTO movimientos (producto_id, fecha, tipo, cantidad, usuario, notas, empresa, estado_pago, costo_unitario, destino) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    cur.execute(sql_ins, (producto_id, fecha_str, tipo, cantidad, usuario, notas, empresa, estado_pago, costo_unitario, destino))

    cur.execute("UPDATE productos SET stock=? WHERE id=?", (nuevo_stock, producto_id))

    conn.commit()
    conn.close()


def movimientos_df(
    f_ini: str | None = None,
    f_fin: str | None = None,
    producto_id: int | None = None,
    tipo: str | None = None,
    estado_pago: str | None = None,
    empresa: str | None = None,
) -> pd.DataFrame:
    conn = get_conn()
    sql = (
        "SELECT m.id, m.fecha, m.tipo, m.cantidad, m.usuario, m.notas, m.empresa, m.estado_pago, m.costo_unitario, m.destino, "
        "p.nombre AS producto, p.ingrediente_activo, p.categoria, p.peligrosidad, p.unidad "
        "FROM movimientos m JOIN productos p ON p.id = m.producto_id "
        "WHERE 1=1"
    )
    params = []
    if f_ini:
        sql += " AND date(m.fecha) >= date(?)"; params.append(f_ini)
    if f_fin:
        sql += " AND date(m.fecha) <= date(?)"; params.append(f_fin)
    if producto_id:
        sql += " AND m.producto_id = ?"; params.append(producto_id)
    if tipo in ("ingreso","consumo","ajuste"):
        sql += " AND m.tipo = ?"; params.append(tipo)
    if estado_pago in ("pagado","debe"):
        sql += " AND m.estado_pago = ?"; params.append(estado_pago)
    if empresa:
        sql += " AND m.empresa LIKE ?"; params.append(f"%{empresa}%")

    sql += " ORDER BY datetime(m.fecha) DESC, m.id DESC"
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df

# =============== Helpers UI ===============

def hazard_badge(code: str) -> str:
    return HAZARD_LEVELS.get(code, code)


def df_with_badges(df: pd.DataFrame) -> pd.DataFrame:
    if "peligrosidad" in df.columns:
        df = df.copy()
        df["peligrosidad"] = df["peligrosidad"].map(hazard_badge)
    return df

# =============== Sidebar ===============
st.sidebar.title("🌿 Qualisem Productos")
st.sidebar.caption("Almacén de fitosanitarios — compras, consumo e inventario")
with st.sidebar:
    st.markdown("**Leyenda de peligrosidad**")
    for k in HAZARD_KEYS:
        st.markdown(f"- {hazard_badge(k)}")

st.title("📦 Control de Almacén de Fitosanitarios")
st.write("Registra **ingresos** (compras), **consumos**, monitorea **inventario**, **historial** y **cuentas por pagar**.")

TAB_CATALOGO, TAB_INGRESO, TAB_CONSUMO, TAB_INVENTARIO, TAB_CXP, TAB_HIST = st.tabs([
    "📚 Catálogo",
    "🛒 Ingresos (Compras)",
    "🧪 Consumo / Uso",
    "📊 Inventario",
    "💳 Cuentas por pagar",
    "🕓 Historial",
])

# =============== Catálogo ===============
with TAB_CATALOGO:
    st.subheader("Agregar producto")
    with st.form("form_producto", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Nombre comercial *", placeholder="Ej: Mancozeb 80 WP")
            ingrediente = st.text_input("Ingrediente activo *", placeholder="Ej: Mancozeb")
            categoria = st.text_input("Categoría *", placeholder="Fungicida / Insecticida / Herbicida …")
        with col2:
            peligrosidad = st.selectbox("Peligrosidad *", options=HAZARD_KEYS, format_func=lambda x: HAZARD_LEVELS[x])
            unidad = st.selectbox("Unidad", ["L","mL","kg","g","u"], index=0)
        empresa_prod = st.text_input("Empresa (proveedor habitual)")
        stock_min = st.number_input("Stock mínimo (alerta)", min_value=0.0, step=0.1, value=0.0)
        submitted = st.form_submit_button("Guardar producto", type="primary")

    if submitted:
        if not (nombre and ingrediente and categoria):
            st.error("Completa los campos obligatorios (*)")
        else:
            add_producto(nombre, ingrediente, categoria, peligrosidad, unidad, empresa_prod or None, stock_min)
            st.success(f"Producto **{nombre}** registrado")

    st.divider(); st.subheader("Catálogo")
    df_prod = list_productos_df()
    if df_prod.empty:
        st.info("No hay productos")
    else:
        q = st.text_input("Buscar por nombre / ingrediente / categoría / empresa", key="q_catalogo")
        if q:
            mask = (
                df_prod["nombre"].str.contains(q, case=False, na=False)
                | df_prod["ingrediente_activo"].str.contains(q, case=False, na=False)
                | df_prod["categoria"].str.contains(q, case=False, na=False)
                | df_prod["empresa"].str.contains(q, case=False, na=False)
            )
            df_show = df_prod[mask]
        else:
            df_show = df_prod
        st.dataframe(df_with_badges(df_show), use_container_width=True, hide_index=True)

        with st.expander("Editar / Eliminar"):
            prod_opt = {f"{r.nombre} — {r.ingrediente_activo} (id {r.id})": int(r.id) for r in df_prod.itertuples()}
            if prod_opt:
                pid = st.selectbox("Producto", options=list(prod_opt.values()), format_func=lambda i: list(prod_opt.keys())[list(prod_opt.values()).index(i)])
                p = get_producto(pid)
                if p:
                    c1,c2 = st.columns(2)
                    with c1:
                        new_nombre = st.text_input("Nombre", value=p["nombre"])
                        new_ing = st.text_input("Ingrediente activo", value=p["ingrediente_activo"])
                        new_cat = st.text_input("Categoría", value=p["categoria"])
                        new_emp = st.text_input("Empresa", value=p.get("empresa") or "")
                    with c2:
                        new_pel = st.selectbox("Peligrosidad", HAZARD_KEYS, index=HAZARD_KEYS.index(p["peligrosidad"]), format_func=lambda x: HAZARD_LEVELS[x])
                        new_uni = st.selectbox("Unidad", ["L","mL","kg","g","u"], index=["L","mL","kg","g","u"].index(p["unidad"]))
                        new_min = st.number_input("Stock mínimo", min_value=0.0, step=0.1, value=float(p.get("stock_minimo",0)))
                    b1,b2 = st.columns(2)
                    if b1.button("Actualizar", type="primary"):
                        update_producto(pid, new_nombre, new_ing, new_cat, new_pel, new_uni, new_emp or None, new_min)
                        st.success("Producto actualizado")
                    if b2.button("Eliminar", type="secondary"):
                        delete_producto(pid)
                        st.warning("Producto eliminado")

# =============== Ingresos (Compras) ===============
with TAB_INGRESO:
    st.subheader("Registrar ingreso / compra")
    df_prod = list_productos_df()
    if df_prod.empty:
        st.info("Primero agrega productos en Catálogo")
    else:
        prod_label = {int(r.id): f"{r.nombre} — {r.ingrediente_activo} (Stock: {r.stock} {r.unidad})" for r in df_prod.itertuples()}
        producto_id = st.selectbox("Producto", options=list(prod_label.keys()), format_func=lambda k: prod_label[k])
        c1,c2,c3 = st.columns(3)
        with c1:
            cantidad = st.number_input("Cantidad", min_value=0.0, step=0.1, value=0.0)
        with c2:
            costo_unitario = st.number_input("Costo unitario (opcional)", min_value=0.0, step=0.1, value=0.0)
        with c3:
            fecha = st.date_input("Fecha", value=date.today())
        c4,c5 = st.columns(2)
        with c4:
            empresa = st.text_input("Empresa (proveedor)")
        with c5:
            estado_pago = st.selectbox("Estado de pago", ["pagado","debe"], index=1)
        usuario = st.text_input("Usuario/Responsable")
        notas = st.text_area("Notas (lote, guía, etc.)", height=80)

        if st.button("Registrar ingreso", type="primary"):
            try:
                fecha_str = datetime.combine(fecha, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
                registrar_movimiento(int(producto_id), 'ingreso', float(cantidad), usuario or None, notas or None, fecha_str, empresa or None, estado_pago, (costo_unitario or None), None)
                st.success("Ingreso registrado")
            except Exception as e:
                st.error(f"No se pudo registrar: {e}")

# =============== Consumo (Uso) ===============
with TAB_CONSUMO:
    st.subheader("Registrar consumo / uso")
    df_prod = list_productos_df()
    if df_prod.empty:
        st.info("Primero agrega productos en Catálogo")
    else:
        prod_label = {int(r.id): f"{r.nombre} — {r.ingrediente_activo} (Stock: {r.stock} {r.unidad})" for r in df_prod.itertuples()}
        producto_id = st.selectbox("Producto", options=list(prod_label.keys()), format_func=lambda k: prod_label[k], key="cons_prod")
        c1,c2,c3 = st.columns(3)
        with c1:
            cantidad = st.number_input("Cantidad", min_value=0.0, step=0.1, value=0.0, key="cons_cant")
        with c2:
            destino = st.text_input("Destino / Actividad (opcional)", placeholder="Parcela, lote, cultivo, etc.", key="cons_dest")
        with c3:
            fecha = st.date_input("Fecha", value=date.today(), key="cons_fecha")
        usuario = st.text_input("Usuario/Responsable", key="cons_user")
        notas = st.text_area("Notas (condición, mezcla, etc.)", height=80, key="cons_notas")

        if st.button("Registrar consumo", type="primary"):
            try:
                fecha_str = datetime.combine(fecha, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
                registrar_movimiento(int(producto_id), 'consumo', float(cantidad), usuario or None, notas or None, fecha_str, None, None, None, destino or None)
                st.success("Consumo registrado")
            except Exception as e:
                st.error(f"No se pudo registrar: {e}")

# =============== Inventario ===============
with TAB_INVENTARIO:
    st.subheader("Inventario actual")
    dfp = list_productos_df()
    if dfp.empty:
        st.info("Sin productos.")
    else:
        categorias_unicas = sorted([c for c in dfp["categoria"].dropna().unique()])
        colf1,colf2,colf3 = st.columns([1,1,1])
        with colf1:
            f_pelig = st.multiselect("Peligrosidad", options=HAZARD_KEYS, format_func=lambda x: HAZARD_LEVELS[x])
        with colf2:
            f_cat_multi = st.multiselect("Categorías", options=categorias_unicas)
        with colf3:
            f_text = st.text_input("Buscar (nombre/IA/empresa)")
        df_show = dfp.copy()
        if f_pelig:
            df_show = df_show[df_show["peligrosidad"].isin(f_pelig)]
        if f_cat_multi:
            df_show = df_show[df_show["categoria"].isin(f_cat_multi)]
        if f_text:
            mask = (
                df_show["nombre"].str.contains(f_text, case=False, na=False)
                | df_show["ingrediente_activo"].str.contains(f_text, case=False, na=False)
                | df_show["empresa"].str.contains(f_text, case=False, na=False)
            )
            df_show = df_show[mask]
        # Alertas de stock mínimo
        df_alert = df_show[df_show["stock"] < df_show["stock_minimo"]]
        if not df_alert.empty:
            st.warning(f"⚠️ {len(df_alert)} producto(s) por debajo del stock mínimo")
        c1,c2,c3 = st.columns(3)
        c1.metric("Productos (filtrados)", len(df_show))
        c2.metric("Suma de stock", f"{df_show['stock'].sum():.2f}")
        c3.metric("Categorías", df_show['categoria'].nunique())
        st.markdown("### 📂 Resumen por categoría")
        df_sum = df_show.groupby("categoria", dropna=False)["stock"].sum().reset_index().sort_values("stock", ascending=False)
        st.dataframe(df_sum, use_container_width=True, hide_index=True)
        try:
            st.bar_chart(data=df_sum.set_index("categoria")["stock"], height=240)
        except Exception:
            pass
        st.markdown("### 📋 Detalle de productos")
        st.dataframe(df_with_badges(df_show), use_container_width=True, hide_index=True)

# =============== Cuentas por pagar ===============
with TAB_CXP:
    st.subheader("Cuentas por pagar (ingresos con 'debe')")
    df_cxp = movimientos_df(tipo='ingreso', estado_pago='debe')
    if df_cxp.empty:
        st.info("No hay deudas registradas.")
    else:
        # Monto = cantidad * costo_unitario (si existe)
        df_cxp = df_cxp.copy()
        df_cxp["monto"] = (df_cxp["cantidad"] * df_cxp.get("costo_unitario", 0)).fillna(0.0)
        # Resumen por empresa
        resumen = df_cxp.groupby("empresa", dropna=False).agg(
            registros=("id","count"),
            cantidad_total=("cantidad","sum"),
            monto_total=("monto","sum")
        ).reset_index().sort_values("monto_total", ascending=False)
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.markdown("### Detalle")
        st.dataframe(df_cxp[["fecha","empresa","producto","cantidad","costo_unitario","monto","estado_pago","usuario","notas"]], use_container_width=True, hide_index=True)

# =============== Historial ===============
with TAB_HIST:
    st.subheader("Historial de movimientos")
    c1,c2,c3,c4 = st.columns(4)
    with c1:
        f_ini = st.date_input("Desde", value=None, format="YYYY-MM-DD")
    with c2:
        f_fin = st.date_input("Hasta", value=None, format="YYYY-MM-DD")
    with c3:
        dfp = list_productos_df()
        prod_map = {0: "Todos"}
        if not dfp.empty:
            prod_map.update({int(r.id): f"{r.nombre}" for r in dfp.itertuples()})
        sel_pid = st.selectbox("Producto", options=list(prod_map.keys()), format_func=lambda k: prod_map[k])
    with c4:
        tipo = st.selectbox("Tipo", options=["Todos","ingreso","consumo","ajuste"], index=0)
    c5,c6 = st.columns(2)
    with c5:
        f_estado_pago = st.selectbox("Estado de pago", options=["Todos","pagado","debe"], index=0)
    with c6:
        f_empresa = st.text_input("Empresa contiene")

    f_ini_str = f_ini.strftime("%Y-%m-%d") if isinstance(f_ini, date) else None
    f_fin_str = f_fin.strftime("%Y-%m-%d") if isinstance(f_fin, date) else None
    tipo_query = None if tipo == "Todos" else tipo
    pid_query = None if sel_pid == 0 else int(sel_pid)
    estado_pago_query = None if f_estado_pago == "Todos" else f_estado_pago

    df_hist = movimientos_df(f_ini=f_ini_str, f_fin=f_fin_str, producto_id=pid_query, tipo=tipo_query, estado_pago=estado_pago_query, empresa=f_empresa or None)
    if df_hist.empty:
        st.info("Sin movimientos para los filtros actuales.")
    else:
        st.dataframe(df_with_badges(df_hist), use_container_width=True, hide_index=True)
        entradas = df_hist[df_hist["tipo"]=="ingreso"]["cantidad"].sum()
        consumos = df_hist[df_hist["tipo"]=="consumo"]["cantidad"].sum()
        pagado_sum = df_hist[df_hist["estado_pago"]=="pagado"]["cantidad"].sum() if "estado_pago" in df_hist.columns else 0
        debe_sum = df_hist[df_hist["estado_pago"]=="debe"]["cantidad"].sum() if "estado_pago" in df_hist.columns else 0
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Ingresos (sum)", f"{entradas:.2f}")
        c2.metric("Consumos (sum)", f"{consumos:.2f}")
        c3.metric("Pagado (sum)", f"{pagado_sum:.2f}")
        c4.metric("Debe (sum)", f"{debe_sum:.2f}")

st.caption("© 2025 Qualisem Productos — Almacén en Streamlit + SQLite. 🐍")
