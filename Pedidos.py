import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import locale
from cachetools import TTLCache
import requests
from dotenv import load_dotenv
import os

# Configuração da página
st.set_page_config(page_title="Relatório de Pedidos", layout="wide")

# Tentar definir o locale para formatação monetária
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    st.warning("Locale 'pt_BR.UTF-8' não disponível. Usando formatação padrão.")
    locale.setlocale(locale.LC_ALL, '')

# Configuração dos caches (TTL de 180 segundos)
cache_pcmovendpend = TTLCache(maxsize=1, ttl=180)
cache_pcpedc = TTLCache(maxsize=1, ttl=180)

# Carregar variáveis de ambiente
load_dotenv()

# Configuração do Supabase
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpvem9tbnBwd3B3Z3RxZGd0d255Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDY1NTYzMDYsImV4cCI6MjA2MjEzMjMwNn0.KcX5BOG-hiqo6baMinRuJjxmtgGKbWNZjNuzVLk9GiI")
SUPABASE_ENDPOINTS = [
    {
        "url": os.getenv("SUPABASE_URL_PCMOVENDPEND", "https://zozomnppwpwgtqdgtwny.supabase.co/rest/v1/PCMOVENDPEND?select=*"),
        "table_name": "pcmovendpend",
        "columns": ['DTFIMOS', 'CONFERENTE', 'DTINICIOOS', 'POSICAO'],
        "date_column": "DTFIMOS"
    },
    {
        "url": os.getenv("SUPABASE_URL_PCPEDC", "https://zozomnppwpwgtqdgtwny.supabase.co/rest/v1/PCPEDC_POSICAO?select=*"),
        "table_name": "pcpedc",
        "columns": ['DATA', 'DESCRICAO', 'L_COUNT', 'M_COUNT', 'F_COUNT'],
        "date_column": "DATA"
    }
]

# Cabeçalhos para autenticação
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Validar chave e endpoints
if not SUPABASE_KEY:
    st.error("Erro: SUPABASE_KEY não está definido.")
    st.stop()
if not SUPABASE_ENDPOINTS:
    st.error("Erro: Nenhum endpoint do Supabase configurado.")
    st.stop()

# Testar conexão com o primeiro endpoint
try:
    response = requests.get(SUPABASE_ENDPOINTS[0]["url"], headers=SUPABASE_HEADERS, timeout=10)
    response.raise_for_status()
except Exception as e:
    st.error(f"Erro ao conectar ao Supabase: {e}")
    st.stop()

# Função para formatar valores monetários
def formatar_valor(valor):
    try:
        return locale.currency(valor, grouping=True)
    except:
        return f"R$ {valor:,.2f}"

# Função para buscar dados do Supabase com cache
@st.cache_data(show_spinner=False)
def get_data_from_supabase(data_inicial="2024-01-01", data_final="2025-12-31"):
    data = {}
    for endpoint in SUPABASE_ENDPOINTS:
        table_name = endpoint["table_name"]
        cache_key = f"{table_name}_{data_inicial}_{data_final}"
        cache = cache_pcmovendpend if table_name == "pcmovendpend" else cache_pcpedc
        
        if cache_key not in cache:
            try:
                # Query com filtro de datas
                query_url = f"{endpoint['url']}&{endpoint['date_column']}=gte.{data_inicial}&{endpoint['date_column']}=lte.{data_final}"
                response = requests.get(query_url, headers=SUPABASE_HEADERS, timeout=30)
                response.raise_for_status()
                
                # Converter resposta para DataFrame
                response_data = response.json()
                if not response_data:
                    st.warning(f"Nenhum dado encontrado na tabela {table_name} para o período {data_inicial} a {data_final}.")
                    cache[cache_key] = pd.DataFrame()
                    data[table_name] = cache[cache_key]
                    continue
                
                df = pd.DataFrame(response_data)
                
                # Verificar se as colunas solicitadas existem
                columns = endpoint["columns"]
                missing_columns = [col for col in columns if col not in df.columns]
                if missing_columns:
                    st.error(f"Colunas não encontradas na tabela {table_name}: {', '.join(missing_columns)}")
                    cache[cache_key] = pd.DataFrame()
                    data[table_name] = cache[cache_key]
                    continue
                
                # Selecionar apenas as colunas especificadas
                df = df[columns]
                
                # Verificar colunas obrigatórias
                required_columns = ['DTFIMOS', 'CONFERENTE'] if table_name == 'pcmovendpend' else ['DATA', 'DESCRICAO', 'L_COUNT', 'M_COUNT']
                missing_required = [col for col in required_columns if col not in df.columns]
                if missing_required:
                    st.error(f"Colunas obrigatórias não encontradas na tabela {table_name}: {', '.join(missing_required)}")
                    cache[cache_key] = pd.DataFrame()
                    data[table_name] = cache[cache_key]
                    continue
                
                cache[cache_key] = df
                data[table_name] = df
            except (requests.exceptions.RequestException, ValueError) as e:
                st.error(f"Erro ao buscar dados do Supabase para a tabela {table_name}: {e}")
                cache[cache_key] = pd.DataFrame()
                data[table_name] = cache[cache_key]
            except Exception as e:
                st.error(f"Erro inesperado ao processar dados para a tabela {table_name}: {e}")
                cache[cache_key] = pd.DataFrame()
                data[table_name] = cache[cache_key]
        else:
            data[table_name] = cache[cache_key]
    return data

# Função para processar dados e agrupar por dia e total
def process_data(data):
    if not data.empty:
        data['DTFIMOS'] = pd.to_datetime(data['DTFIMOS'], errors='coerce')
        data = data.dropna(subset=['DTFIMOS'])  # Remover linhas com DTFIMOS inválido
        data['DIA'] = data['DTFIMOS'].dt.date
        daily_data = data.groupby(['CONFERENTE', 'DIA']).size().reset_index(name='PEDIDOS CONFERIDOS')
        total_data = data.groupby('CONFERENTE').size().reset_index(name='PEDIDOS_TOTAL')
        return daily_data, total_data
    return pd.DataFrame(), pd.DataFrame()

def main():
    # Custom CSS para estilização responsiva
    st.markdown("""
    <style>
        /* General table styling */
        .ranking-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: clamp(14px, 2vw, 16px);
        }
        .ranking-table th, .ranking-table td {
            padding: 12px;
            text-align: center;
            border: 1px solid #ddd;
        }
        .ranking-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .ranking-table tr:hover {
            background-color: #ddd;
        }

        /* Card styling */
        .card {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 10px;
            background-color: #007bff;
            border-radius: 10px;
            box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.1);
            width: 100%;
            text-align: center;
            min-height: 150px;
            color: white;
            margin-bottom: 20px;
            transition: all 0.3s ease;
        }
        .card-content {
            width: 100%;
        }
        .title {
            font-size: clamp(14px, 2vw, 16px);
            font-weight: bold;
            margin-top: 10px;
        }
        .number {
            font-size: clamp(16px, 2.5vw, 18px);
            font-weight: bold;
            margin: 4px 0;
        }

        /* Total container */
        .total-container {
            display: flex;
            flex-direction: column;
            gap: 20px;
            text-align: center;
            align-items: center;
            width: 100%;
            margin-top: 20px;
        }
        .total-item {
            font-size: clamp(18px, 3vw, 22px);
            font-weight: bold;
            color: #fff;
        }
        .total-paragrafo {
            font-size: clamp(14px, 2vw, 16px);
        }
        .total-item-final {
            font-size: clamp(14px, 2vw, 16px);
        }

        /* Scrollable table */
        .scrollable-table {
            max-height: 400px;
            overflow-y: auto;
            display: block;
            border: 1px solid #ddd;
            width: 100%;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }

        /* Responsive adjustments */
        @media (max-width: 768px) {
            .card {
                min-height: 120px;
            }
            .total-container {
                gap: 10px;
            }
            .ranking-table th, .ranking-table td {
                padding: 8px;
                font-size: 14px;
            }
        }

        @media (max-width: 480px) {
            .card {
                min-height: 100px;
            }
            .number {
                font-size: 14px;
            }
            .title {
                font-size: 12px;
            }
            .total-item {
                font-size: 16px;
            }
            .total-paragrafo {
                font-size: 12px;
            }
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1>Relatório de Pedidos</h1>", unsafe_allow_html=True)

    # Buscar dados do Supabase com cache
    with st.spinner("Carregando dados..."):
        data = get_data_from_supabase()
    data_1 = data.get('pcmovendpend', pd.DataFrame())
    data_2 = data.get('pcpedc', pd.DataFrame())

    hoje = datetime.today().date()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    inicio_mes = hoje.replace(day=1)

    if not data_1.empty or not data_2.empty:
        daily_data, total_data = process_data(data_1)
        if not data_2.empty:
            data_2['DATA'] = pd.to_datetime(data_2['DATA'], errors='coerce')
            data_2 = data_2.dropna(subset=['DATA'])  # Remover linhas com DATA inválida
            rotas_desejadas = ["GRANDE VITORIA", "REGIÃO SUL", "REGIAO NORTE", "BR 262", "EXTREMO SUL", "EXTREMO NORTE", "EXTREMO CENTRO/ES"]

            total_liberados = data_2['L_COUNT'].sum()
            total_montados = data_2['M_COUNT'].sum()

            st.markdown("<h3>Regiões</h3>", unsafe_allow_html=True)
            rotas_selecionadas = st.multiselect("Selecione as Rotas", rotas_desejadas, default=rotas_desejadas)
            data_filtrada = data_2[data_2['DESCRICAO'].isin(rotas_selecionadas)]

            data_aggregated = data_filtrada.groupby(['DESCRICAO']).agg(
                pedidos_liberados=('L_COUNT', 'sum'),
                pedidos_montados=('M_COUNT', 'sum')
            ).reset_index()

        total_dia = daily_data[daily_data['DIA'] == hoje]['PEDIDOS CONFERIDOS'].sum() if not daily_data.empty else 0
        total_semana = daily_data[(daily_data['DIA'] >= inicio_semana) & (daily_data['DIA'] <= hoje)]['PEDIDOS CONFERIDOS'].sum() if not daily_data.empty else 0
        total_mes = daily_data[(daily_data['DIA'] >= inicio_mes) & (daily_data['DIA'] <= hoje)]['PEDIDOS CONFERIDOS'].sum() if not daily_data.empty else 0

        # Duas colunas lado a lado
        col1, col2 = st.columns([1, 1])

        with col1:
            if not data_2.empty:
                st.markdown("### Pedidos por Rota")
                num_colunas = 3 if st.session_state.get('screen_width', 1000) > 768 else 1
                cols = st.columns(num_colunas)

                colors = {
                    "GRANDE VITORIA": "#FF6347",
                    "REGIÃO SUL": "#32CD32",
                    "REGIAO NORTE": "#000080",
                    "BR 262": "#6A5ACD",
                    "EXTREMO SUL": "#FF69B4",
                    "EXTREMO NORTE": "#20B2AA",
                    "EXTREMO CENTRO/ES": "#FF4500",
                }

                for index, row in data_aggregated.iterrows():
                    if index >= len(cols) * 3:  # Limitar para evitar erros de índice
                        break
                    rota_nome = row['DESCRICAO']
                    pedidos_liberados = row['pedidos_liberados']
                    pedidos_montados = row['pedidos_montados']
                    col = cols[index % num_colunas]
                    with col:
                        st.markdown(f"""
                            <div class="card" style="background-color: {colors.get(rota_nome, '#007bff')}">
                                <span class="title">{rota_nome}</span><br>
                                <div class="card-content">
                                    <div class="card-item" style="display: flex; align-items: center; justify-content: space-around">
                                        <img src="https://cdn-icons-png.flaticon.com/512/5629/5629260.png" width="30" style="margin-right: 5px;">
                                        <p style="margin: 0px; font-weight: bold;">LIBERADOS:</p>
                                        <div class="number">{int(pedidos_liberados)}</div>
                                    </div>
                                    <div class="card-item" style="display: flex; align-items: center; justify-content: space-around">
                                        <img src="https://cdn-icons-png.flaticon.com/512/9964/9964349.png" width="30" style="margin-right: 5px;">
                                        <p style="margin: 0px; font-weight: bold;">MONTADOS:</p>
                                        <div class="number">{int(pedidos_montados)}</div>
                                    </div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
            else:
                st.warning("Nenhum dado disponível para exibir pedidos por rota.")

        with col2:
            st.markdown("### Pedidos Conferidos por Funcionário")
            data_inicial = st.date_input("Data Inicial", value=hoje, key="data_inicial")
            data_final = st.date_input("Data Final", value=hoje, key="data_final")

            if data_inicial > data_final:
                st.error("A data inicial não pode ser maior que a data final.")
                return

            filtered_data = daily_data[(daily_data['DIA'] >= data_inicial) & (daily_data['DIA'] <= data_final)] if not daily_data.empty else pd.DataFrame()
            if not filtered_data.empty:
                filtered_data_sorted = filtered_data.sort_values(by=['DIA', 'PEDIDOS CONFERIDOS'], ascending=[True, False]).reset_index(drop=True)
                # Format DIA as string to avoid serialization issues
                filtered_data_sorted['DIA'] = filtered_data_sorted['DIA'].astype(str)
                st.markdown('<div class="scrollable-table">' + filtered_data_sorted.to_html(index=False, escape=False, classes="ranking-table") + '</div>', unsafe_allow_html=True)
            else:
                st.warning("Nenhum dado encontrado para o intervalo de datas selecionado.")

        # Relatório de Pedidos
        st.markdown("<h2>Relatório de Pedidos</h2>", unsafe_allow_html=True)
        st.markdown(f"""
            <div class="total-container">
                <div class="total-item">
                    <img src="https://cdn-icons-png.flaticon.com/512/10995/10995680.png" width="35" style="margin-right: 5px;">
                    <span class="total-paragrafo">TOTAL LIBERADOS:</span>
                    <span class="total-numero-conf">{int(total_liberados)}</span>
                </div>
                <div class="total-item">
                    <img src="https://cdn-icons-png.flaticon.com/512/976/976438.png" width="35" style="margin-right: 5px;">
                    <span class="total-paragrafo">TOTAL MONTADOS:</span>
                    <span class="total-numero-conf">{int(total_montados)}</span>
                </div>
                <div class="total-item">
                    <img src="https://cdn-icons-png.flaticon.com/512/5220/5220625.png" width="35" style="margin-right: 5px;">
                    <span class="total-paragrafo">CONF DIÁRIA:</span>
                    <span class="total-numero-conf">{int(total_dia)}</span>
                    <span class="total-item-final">PEDIDOS</span>
                </div>
                <div class="total-item">
                    <img src="https://cdn-icons-png.flaticon.com/512/391/391175.png" width="35" style="margin-right: 5px;">
                    <span class="total-paragrafo">CONF SEMANAL:</span>
                    <span class="total-numero-conf">{int(total_semana)}</span>
                    <span class="total-item-final">PEDIDOS</span>
                </div>
                <div class="total-item">
                    <img src="https://cdn-icons-png.flaticon.com/512/353/353267.png" width="35" style="margin-right: 5px;">
                    <span class="total-paragrafo">CONF MENSAL:</span>
                    <span class="total-numero-conf">{int(total_mes)}</span>
                    <span class="total-item-final">PEDIDOS</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.warning("Nenhum dado disponível para exibição.")

if __name__ == "__main__":
    main()