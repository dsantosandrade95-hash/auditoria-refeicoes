import streamlit as st
import pandas as pd
import io
import re
import unicodedata

st.set_page_config(page_title="Auditoria SOC-RS2", layout="wide", page_icon="🤖")

st.title("🤖 Painel de Auditoria de Refeições Quinzena")
st.markdown("---")

def normalizar_nome(texto):
    if pd.isna(texto): return ""
    txt = str(texto).strip().upper()
    txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('utf-8')
    return re.sub(r'\s+', ' ', txt)

def identificar_turno(escala):
    escala_str = str(escala).strip()
    if not scala_str or pd.isna(escala): return "NÃO IDENTIFICADO"
    horarios = re.findall(r'\b\d{2}:\d{2}\b', escala_str)
    if not horarios: return "NÃO IDENTIFICADO"
    entrada = horarios[0]
    if entrada == "05:25": return "T1"
    elif entrada in ["13:30", "13:40"]: return "T2"
    elif entrada == "22:00": return "T3"
    elif entrada == "17:00": return "T4"
    elif entrada in ["18:00", "19:00"]: return "T5"
    elif entrada == "09:00": return "ADM"
    else: return "OUTRO"

def processar_arquivo_catraca(nome_arq, conteudo):
    if nome_arq.endswith('.csv'):
        linhas = io.StringIO(conteudo.decode('utf-8', errors='ignore')).readlines()
    else:
        df_temp = pd.read_excel(io.BytesIO(conteudo), header=None)
        linhas = ["\t".join(l) for l in df_temp.astype(str).values.tolist()]

    nome_up = nome_arq.upper()
    refeicao = "CAFÉ" if "CAFE" in nome_up else ("ALMOÇO" if "ALMOCO" in nome_up or "ALMOÇO" in nome_up else ("JANTA" if "JANTA" in nome_up else ("CEIA" if "CEIA" in nome_up else "NÃO IDENTIFICADO")))

    registros = []
    nome_atual = None
    
    for l in linhas:
        l_str = str(l).strip()
        if "NOME:" in l_str.upper():
            match = re.search(r'(?i)Nome:\s*(.*)', l_str)
            if match: nome_atual = match.group(1).split('\t')[0].strip()
            continue
        match_data = re.match(r'^(\d{2}/\d{2}/\d{4})', l_str)
        if match_data and nome_atual:
            data_acesso = match_data.group(1)
            match_hora = re.search(r'\b(\d{2}:\d{2}:\d{2})\b', l_str)
            hora_acesso = match_hora.group(1) if match_hora else "00:00:00"
            registros.append({
                'Nome_Catraca': nome_atual, 'Data': data_acesso, 'Hora': hora_acesso,
                'Refeicao': refeicao, 'Acessos': 1
            })
    return pd.DataFrame(registros)

# Roteiro da Interface Visual
col1, col2 = st.columns([1, 3])

with col1:
    st.header("📁 Upload de Arquivos")
    file_abs = st.file_uploader("1. Suba a Planilha ABS (Ativos)", type=["xlsx"])
    files_catraca = st.file_uploader("2. Suba os Relatórios da Catraca", type=["csv", "xlsx"], accept_multiple_files=True)

with col2:
    if file_abs and files_catraca:
        st.success("Arquivos carregados prontos para análise!")
        
        if st.button("🚀 INICIAR PROGESSAMENTO DA AUDITORIA"):
            try:
                df_ativos = pd.read_excel(file_abs, sheet_name='Ativos')
            except:
                df_ativos = pd.read_excel(file_abs, sheet_name=0)

            df_ativos = df_ativos[['Office', 'Nome do Colaborador', 'Cargo', 'Team', 'Escala', 'Status']].dropna(subset=['Nome do Colaborador'])
            df_ativos['nome_key'] = df_ativos['Nome do Colaborador'].apply(normalizar_nome)
            df_ativos['Turno_Identificado'] = df_ativos['Escala'].apply(identificar_turno)

            lista_df = []
            for f in files_catraca:
                df_res = processar_arquivo_catraca(f.name, f.read())
                if not df_res.empty: lista_df.append(df_res)

            if lista_df:
                base_cruzada = pd.concat(lista_df, ignore_index=True)
                base_cruzada['nome_key'] = base_cruzada['Nome_Catraca'].apply(normalizar_nome)
                base_cruzada = pd.merge(base_cruzada, df_ativos, on='nome_key', how='left')

                base_cruzada['Grupo'] = base_cruzada['Office'].apply(lambda x: "HUB-LRS-15" if any(h in str(x).upper() for h in ["HUB", "LRS"]) else "SOC-RS2")
                
                refeicoes_permitidas = {'T1': ['CAFÉ', 'ALMOÇO'], 'T2': ['JANTA'], 'T3': ['CEIA'], 'T4': ['JANTA'], 'T5': ['JANTA'], 'ADM': ['ALMOÇO']}
                
                base_cruzada['Refeicao_Permitida'] = base_cruzada.apply(lambda r: "SIM" if r['Refeicao'] in refeicoes_permitidas.get(r['Turno_Identificado'], []) else ("SEM ESCALA/SEM MATCH" if r['Office'] is None or pd.isna(r['Office']) else "NÃO"), axis=1)
                base_cruzada['Custo_Extra'] = base_cruzada.apply(lambda r: (7.73 if r['Refeicao'] == "CAFÉ" else 21.65) if r['Refeicao_Permitida'] == "NÃO" else 0.0, axis=1)

                # KPIs na Tela
                custo_total = base_cruzada['Custo_Extra'].sum()
                fora_turno_n = len(base_cruzada[base_cruzada['Refeicao_Permitida'] == "NÃO"])
                
                kpi1, kpi2, kpi3 = st.columns(3)
                kpi1.metric("Total Acessos Lidos", f"{len(base_cruzada)} registros")
                kpi2.metric("Inconsistências (Fora Turno)", f"{fora_turno_n} acessos")
                kpi3.metric("Custo Extra Gerado", f"R$ {custo_total:,.2f}")

                # Gráficos e Tabelas Rápidas
                st.subheader("Visualização Rápida")
                df_resumo = base_cruzada.groupby(['Grupo', 'Refeicao'])['Acessos'].sum().reset_index()
                st.dataframe(df_resumo, use_container_width=True)

                # Gerar Download
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    base_cruzada.to_excel(writer, sheet_name='Base_Cruzada', index=False)
                
                st.download_button(
                    label="📥 BAIXAR EXCEL CONSOLIDADO COMPLETO",
                    data=output.getvalue(),
                    file_name="Auditoria_Fechamento_Quinzena.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("Nenhum dado de acesso foi estruturado dos relatórios fornecidos.")
    else:
        st.info("Aguardando o upload de todas as planilhas obrigatórias na barra lateral esquerda.")
