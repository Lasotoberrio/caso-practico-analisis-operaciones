# ETL caso practico - Analista de Operacion nivel III
# Leonardo Soto
#
# Extrae las 3 fuentes (csv, txt con |, json), las limpia, les agrega
# campos de control y deja las tablas listas para Tableau.
# Uso: python etl_caso_practico.py <carpeta_datos_originales> <carpeta_salida>

import sys
import json
import pandas as pd

entrada = sys.argv[1] if len(sys.argv) > 1 else "Datos"
salida = sys.argv[2] if len(sys.argv) > 2 else "3_Datos_limpios"

# ---------------- 1. EXTRAER ----------------
# los documentos se leen como texto, son identificadores (no se suman)
clientes = pd.read_csv(f"{entrada}/clientes_productos.csv",
                       dtype={"company_doc_number": str, "bank_holder_doc_number": str,
                              "bank_account_number": str})
trx = pd.read_csv(f"{entrada}/transacciones.txt", sep="|",
                  dtype={"client_doc_number": str, "client_phone": str,
                         "counterpart_account": str})
with open(f"{entrada}/tickets_usuarios.json", encoding="utf-8") as f:
    tickets = pd.json_normalize(json.load(f))   # aplana form_details

print("filas leidas ->", "clientes:", len(clientes), "| trx:", len(trx), "| tickets:", len(tickets))

# ---------------- 2. TRANSFORMAR ----------------
# --- clientes ---
for c in ["product_enrollment_date", "last_update"]:
    clientes[c] = pd.to_datetime(clientes[c])
clientes["cuenta_validada"] = clientes["bank_account_validated"].eq("Sí").astype(int)
clientes["boton_credito"] = clientes["has_credit_button"].eq("Sí").astype(int)
# quito datos sensibles que no se usan en el analisis
clientes = clientes.drop(columns=["bank_account_number", "bank_holder_doc_number"])

# --- transacciones ---
trx["posting_date"] = pd.to_datetime(trx["posting_date"])
trx["canal_origen"] = trx["transaction_origin_details"].str.replace("Origen:", "", regex=False)
trx["credit_note"] = trx["credit_note"].fillna("Sin nota")
trx["es_reverso"] = trx["reversal_flag"]
# el flag de reverso y el campo transaction_info no siempre dicen lo mismo
trx["reverso_inconsistente"] = ((trx["transaction_info"] == "Reverso") != (trx["reversal_flag"] == 1)).astype(int)

# traigo condiciones del contrato del cliente para validar
cond = clientes[["company_id", "product_enrollment_date", "trx_min_limit", "trx_max_limit",
                 "commission_percent", "min_commission_value", "max_commission_value",
                 "cuenta_validada"]]
trx = trx.merge(cond, left_on="client_ref_id", right_on="company_id", how="left")

trx["excede_tope_comision"] = (trx["transaction_fee"] > trx["max_commission_value"]).astype(int)
trx["valor_sobre_tope"] = (trx["transaction_fee"] - trx["max_commission_value"]).clip(lower=0).round(2)
trx["fuera_limite_trx"] = ((trx["transaction_value"] > trx["trx_max_limit"]) |
                           (trx["transaction_value"] < trx["trx_min_limit"])).astype(int)
trx["antes_de_vinculacion"] = (trx["posting_date"] < trx["product_enrollment_date"]).astype(int)
trx["abono_cuenta_no_validada"] = ((trx["transaction_type"] == "Abono") &
                                   (trx["cuenta_validada"] == 0)).astype(int)
trx = trx.drop(columns=["company_id", "client_phone", "product_enrollment_date",
                        "trx_min_limit", "trx_max_limit", "min_commission_value",
                        "cuenta_validada", "posting_day", "transaction_day"])

# --- tickets ---
for c in ["created_timestamp", "updated_timestamp", "closed_timestamp"]:
    tickets[c] = pd.to_datetime(tickets[c])
tickets["created_date"] = tickets["created_timestamp"].dt.normalize()
tickets = tickets.rename(columns={"form_details.campo1": "form_campo1", "form_details.campo2": "form_campo2"})
tickets["estado_grupo"] = tickets["ticket_status"].map(
    {"open": "Pendiente", "pending": "Pendiente", "closed": "Resuelto", "solved": "Resuelto"})
# hay tickets abiertos con fecha de cierre y cerrados sin fecha -> se marcan
tickets["estado_inconsistente"] = (
    ((tickets["estado_grupo"] == "Pendiente") & tickets["closed_timestamp"].notna()) |
    ((tickets["estado_grupo"] == "Resuelto") & tickets["closed_timestamp"].isna())).astype(int)
# dias de resolucion solo para los que de verdad estan resueltos y tienen fecha
ok = (tickets["estado_grupo"] == "Resuelto") & tickets["closed_timestamp"].notna()
tickets["dias_resolucion"] = ((tickets["closed_timestamp"] - tickets["created_timestamp"])
                              .dt.total_seconds() / 86400).where(ok).round(1)
tickets["rango_resolucion"] = pd.cut(tickets["dias_resolucion"], [0, 3, 7, 14, 999],
                                     labels=["0-3 dias", "4-7 dias", "8-14 dias", "Mas de 14 dias"])
tickets["tiene_encuesta"] = tickets["satisfaction_score"].notna().astype(int)
tickets["es_urgente"] = tickets["tags"].apply(lambda x: int("urgente" in x))
# llave al cliente: el documento del ticket = documento del comercio
tickets = tickets.merge(clientes[["company_id", "company_doc_number"]],
                        left_on="client_doc_number", right_on="company_doc_number", how="left")

# tags es una lista -> tabla aparte para no duplicar tickets
puente_tags = tickets[["ticket_id", "tags"]].explode("tags").dropna()
puente_tags.columns = ["ticket_id", "tag"]
tickets = tickets.drop(columns=["tags", "company_doc_number", "year", "month", "day",
                                "created_date", "updated_date", "closed_date"])

# marca de clientes sin transacciones
clientes["tiene_transacciones"] = clientes["company_id"].isin(trx["client_ref_id"]).astype(int)

# ---------------- 3. CARGAR ----------------
clientes.to_csv(f"{salida}/dim_clientes.csv", index=False, encoding="utf-8-sig")
trx.to_csv(f"{salida}/fact_transacciones.csv", index=False, encoding="utf-8-sig")
tickets.to_csv(f"{salida}/fact_tickets.csv", index=False, encoding="utf-8-sig")
puente_tags.to_csv(f"{salida}/puente_ticket_tags.csv", index=False, encoding="utf-8-sig")

# chequeos rapidos
assert trx["transaction_id"].is_unique and tickets["ticket_id"].is_unique
assert trx["commission_percent"].notna().all(), "hay transacciones sin cliente"
assert tickets["company_id"].notna().all(), "hay tickets sin cliente"
print("listo ->", len(clientes), len(trx), len(tickets), len(puente_tags))
