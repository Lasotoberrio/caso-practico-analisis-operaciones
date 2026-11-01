# Vistas planas para Tableau Public
# Leonardo Soto
#
# Tableau Public (web) maneja mejor una fuente por archivo, entonces a cada
# tabla de hechos le pego los atributos del comercio y renombro las columnas.
# El modelo estrella de fondo es el mismo que deja etl_caso_practico.py.
# Uso: python vistas_tableau.py <carpeta_datos_limpios>

import sys
import pandas as pd

carpeta = sys.argv[1] if len(sys.argv) > 1 else "3_Datos_limpios"

clientes = pd.read_csv(f"{carpeta}/dim_clientes.csv")
trx = pd.read_csv(f"{carpeta}/fact_transacciones.csv")
tickets = pd.read_csv(f"{carpeta}/fact_tickets.csv")

atributos = clientes[["company_id", "company_doc_type", "branch_name",
                      "product_category", "product_name"]].copy()
atributos["branch_name"] = atributos["branch_name"].str.replace("Sucursal ", "", regex=False)
nombres_comercio = {"company_doc_type": "tipo_cliente", "branch_name": "sucursal",
                    "product_category": "categoria", "product_name": "producto"}

# --- transacciones ---
vt = trx.merge(atributos, left_on="client_ref_id", right_on="company_id", how="left")
vt["fecha"] = pd.to_datetime(vt["posting_date"]).dt.date
vt = vt.rename(columns={**nombres_comercio, "canal_origen": "canal", "transaction_type": "tipo_trx",
                        "transaction_value": "valor", "transaction_fee": "comision",
                        "es_reverso": "reverso", "excede_tope_comision": "sobre_tope",
                        "fuera_limite_trx": "fuera_limite", "antes_de_vinculacion": "antes_vinculacion",
                        "abono_cuenta_no_validada": "abono_no_validada"})
for c in ["valor", "comision", "valor_sobre_tope"]:
    vt[c] = vt[c].round(0).astype(int)
vt = vt[["fecha", "tipo_cliente", "sucursal", "categoria", "producto", "canal", "tipo_trx", "valor",
         "comision", "reverso", "sobre_tope", "valor_sobre_tope", "fuera_limite", "antes_vinculacion",
         "abono_no_validada", "reverso_inconsistente"]]

# --- tickets ---
vk = tickets.merge(atributos, on="company_id", how="left")
vk["fecha"] = pd.to_datetime(vk["created_timestamp"]).dt.date
vk = vk.rename(columns={**nombres_comercio, "estado_grupo": "estado", "incident_type": "tipo_incidente",
                        "contact_channel": "canal_contacto", "team_id": "equipo",
                        "satisfaction_score": "satisfaccion", "es_urgente": "urgente",
                        "incident_value": "valor_incidente"})
vk["valor_incidente"] = vk["valor_incidente"].round(0).astype(int)
vk = vk[["fecha", "tipo_cliente", "sucursal", "categoria", "producto", "estado", "tipo_incidente",
         "canal_contacto", "equipo", "satisfaccion", "dias_resolucion", "rango_resolucion", "urgente",
         "estado_inconsistente", "valor_incidente"]]

vt.to_csv(f"{carpeta}/tableau_transacciones.csv", index=False)
vk.to_csv(f"{carpeta}/tableau_tickets.csv", index=False)
print("vistas listas ->", len(vt), len(vk))
