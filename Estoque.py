import streamlit as st
import pandas as pd
import requests
import datetime
from cachetools import TTLCache
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

# Configuração dos caches (TTL de 180 segundos)
cache_vendas = TTLCache(maxsize=1, ttl=180)
cache_estoque = TTLCache(maxsize=1, ttl=180)

# Configuração das URLs do Supabase e colunas esperadas
SUPABASE_CONFIG = {
    "vendas": {
        "url": "https://zozomnppwpwgtqdgtwny.supabase.co/rest/v1/VwSomelier?select=*",
        "columns": ["CODPROD", "QT", "DESCRICAO_1", "DESCRICAO_2", "DATA"]
    },
    "estoque": {
        "url": "https://zozomnppwpwgtqdgtwny.supabase.co/rest/v1/ESTOQUE?select=*",
        "columns": ["CODPROD", "QT_ESTOQUE", "NOME_PRODUTO", "CODFILIAL", "QTULTENT", "DTULTENT", "DTULTSAIDA", "QTRESERV", "QTINDENIZ", "DTULTPEDCOMPRA", "BLOQUEADA"]
    }
}

# Cabeçalhos para autenticação no Supabase (recomenda-se usar variáveis de ambiente no Streamlit Cloud)
SUPABASE_HEADERS = {
    "apikey": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpvem9tbnBwd3B3Z3RxZGd0d255Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDY1NTYzMDYsImV4cCI6MjA2MjEzMjMwNn0.KcX5BOG-hiqo6baMinRuJjxmtgGKbWNZjNuzVLk9GiI",
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpvem9tbnBwd3B3Z3RxZGd0d255Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDY1NTYzMDYsImV4cCI6MjA2MjEzMjMwNn0.KcX5BOG-hiqo6baMinRuJjxmtgGKbWNZjNuzVLk9GiI"
}

# Função genérica para buscar dados do Supabase com cache e paginação
@st.cache_data(show_spinner=False)
def fetch_supabase_data(cache, url, columns_expected, data_inicial, data_final, date_column=None):
    key = f"{url}_{data_inicial}_{data_final}"
    if key in cache:
        return cache[key]

    all_data = []
    page_size = 700
    start = 0
    headers = SUPABASE_HEADERS.copy()

    # Adicionar filtro de data na URL, se date_column for especificado
    query_url = url
    if date_column:
        query_url += f"?{date_column}=gte.{data_inicial}&{date_column}=lte.{data_final}&select=*"

    try:
        while True:
            headers["Range"] = f"{start}-{start + page_size - 1}"
            response = requests.get(query_url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            if not data or len(data) < page_size:  # Parar se não houver mais dados
                all_data.extend(data)
                break
            all_data.extend(data)
            start += page_size

        if all_data:
            df = pd.DataFrame(all_data)
            # Validar colunas esperadas
            missing_columns = [col for col in columns_expected if col not in df.columns]
            if missing_columns:
                st.error(f"Colunas ausentes nos dados retornados pela URL {url}: {missing_columns}")
                cache[key] = pd.DataFrame()
                return pd.DataFrame()
            # Filtrar por data no lado do cliente, como fallback
            if date_column in df.columns:
                df[date_column] = pd.to_datetime(df[date_column], errors='coerce')
                df = df[(df[date_column] >= pd.to_datetime(data_inicial)) & (df[date_column] <= pd.to_datetime(data_final))]
            cache[key] = df
        else:
            st.warning(f"Nenhum dado retornado pela URL {query_url}.")
            cache[key] = pd.DataFrame()
            df = pd.DataFrame()

    except (requests.exceptions.RequestException, ValueError) as e:
        st.error(f"Erro ao buscar dados da URL {query_url}: {e}")
        cache[key] = pd.DataFrame()
        df = pd.DataFrame()

    return cache[key]

# Função para buscar dados de vendas (VwSomelier)
def fetch_vendas_data(data_inicial, data_final):
    config = SUPABASE_CONFIG["vendas"]
    df = fetch_supabase_data(cache_vendas, config["url"], config["columns"], data_inicial, data_final, date_column="DATA")
    if not df.empty:
        # Converter QT para numérico
        df['QT'] = pd.to_numeric(df['QT'], errors='coerce').fillna(0)
    return df

# Função para buscar dados de estoque (ESTOQUE)
def fetch_estoque_data(data_inicial, data_final):
    config = SUPABASE_CONFIG["estoque"]
    df = fetch_supabase_data(cache_estoque, config["url"], config["columns"], data_inicial, data_final)
    if not df.empty:
        # Converter colunas numéricas relevantes
        for col in ['QT_ESTOQUE', 'QTULTENT', 'QTRESERV', 'QTINDENIZ', 'BLOQUEADA']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

# Função principal
def main():
    st.set_page_config(page_title="Análise de Estoque e Vendas", layout="wide")
    st.title("📦 Análise de Estoque e Vendas")
    st.markdown("Análise dos produtos vendidos e estoque disponível.")

    # Definir as datas de início e fim para os últimos 2 meses
    data_final = datetime.date(2025, 5, 8)  # Última data disponível
    data_inicial = data_final - datetime.timedelta(days=60)  # 09/03/2025

    # Buscar dados de vendas (VwSomelier)
    with st.spinner("Carregando dados de vendas..."):
        vendas_df = fetch_vendas_data(data_inicial, data_final)

    if vendas_df.empty:
        st.warning("Não há vendas para o período selecionado.")
        return

    # Agrupar as vendas por produto e somar as quantidades vendidas
    vendas_grouped = vendas_df.groupby('CODPROD')['QT'].sum().reset_index()

    # Buscar dados de estoque (ESTOQUE)
    with st.spinner("Carregando dados de estoque..."):
        estoque_df = fetch_estoque_data(data_inicial, data_final)

    if estoque_df.empty:
        st.warning("Não há dados de estoque para o período selecionado.")
        return

    # Verificar se os produtos com alta venda estão sem estoque
    merged_df = pd.merge(vendas_grouped, estoque_df[['CODPROD', 'NOME_PRODUTO', 'QT_ESTOQUE']], on='CODPROD', how='left')

    # Filtrando os produtos que NÃO possuem estoque
    sem_estoque_df = merged_df[merged_df['QT_ESTOQUE'].isna() | (merged_df['QT_ESTOQUE'] <= 0)]

    # Barra de pesquisa para código do produto
    pesquisar = st.text_input("Pesquisar por Código do Produto ou Nome", "")

    # Buscar dados do endpoint ESTOQUE com os parâmetros de data
    df = fetch_estoque_data(data_inicial, data_final)

    if not df.empty:
        # Renomear as colunas
        df = df.rename(columns={
            'CODPROD': 'Código do Produto',
            'NOME_PRODUTO': 'Nome do Produto',
            'QTULTENT': 'Quantidade Última Entrada',
            'QT_ESTOQUE': 'Estoque Disponível',
            'QTRESERV': 'Quantidade Reservada',
            'QTINDENIZ': 'Quantidade Avariada',
            'DTULTENT': 'Data Última Entrada',
            'DTULTSAIDA': 'Data Última Saída',
            'CODFILIAL': 'Código da Filial',
            'DTULTPEDCOMPRA': 'Data Último Pedido Compra',
            'BLOQUEADA': 'Quantidade Bloqueada'
        })

        if pesquisar:
            df = df[
                (df['Código do Produto'].astype(str).str.contains(pesquisar, case=False, na=False)) |
                (df['Nome do Produto'].str.contains(pesquisar, case=False, na=False))
            ]

        df['Quantidade Total'] = df[['Estoque Disponível', 'Quantidade Reservada', 'Quantidade Bloqueada']].fillna(0).sum(axis=1)

        # Reordenar as colunas
        df = df.reindex(columns=[
            'Código da Filial', 'Código do Produto', 'Nome do Produto', 'Estoque Disponível', 'Quantidade Reservada', 
            'Quantidade Bloqueada', 'Quantidade Avariada', 'Quantidade Total', 'Quantidade Última Entrada', 
            'Data Última Entrada', 'Data Última Saída', 'Data Último Pedido Compra'
        ])

        # Configurar a tabela de estoque com AgGrid e larguras fixas
        st.subheader("✅ Estoque")
        st.markdown("Use a barra de rolagem para ver mais linhas.")
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(editable=False, filter=True, sortable=True, resizable=False)
        # Definir larguras fixas para cada coluna
        gb.configure_column("Código da Filial", width=100)
        gb.configure_column("Código do Produto", width=120)
        gb.configure_column("Nome do Produto", width=250)
        gb.configure_column("Estoque Disponível", width=120)
        gb.configure_column("Quantidade Reservada", width=120)
        gb.configure_column("Quantidade Bloqueada", width=120)
        gb.configure_column("Quantidade Avariada", width=120)
        gb.configure_column("Quantidade Total", width=120)
        gb.configure_column("Quantidade Última Entrada", width=120)
        gb.configure_column("Data Última Entrada", width=130)
        gb.configure_column("Data Última Saída", width=130)
        gb.configure_column("Data Último Pedido Compra", width=130)
        gb.configure_pagination(enabled=False)
        gb.configure_grid_options(domLayout='normal')
        grid_options = gb.build()

        # Formatar números para exibição
        df_display = df.copy()
        for col in ['Estoque Disponível', 'Quantidade Reservada', 'Quantidade Bloqueada', 'Quantidade Avariada', 'Quantidade Total', 'Quantidade Última Entrada']:
            df_display[col] = df_display[col].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "0")

        AgGrid(
            df_display,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.NO_UPDATE,
            allow_unsafe_jscode=True,
            height=400,
            theme='streamlit',
            fit_columns_on_grid_load=False
        )

    if sem_estoque_df.empty:
        st.info("Não há produtos vendidos sem estoque.")
    else:
        # Exibir a tabela com os produtos sem estoque mas vendidos
        st.subheader("❌ Produtos Sem Estoque com Venda nos Últimos 2 Meses")

        # Excluir produtos com estoque > 0
        sem_estoque_df_renomeado = sem_estoque_df[sem_estoque_df['QT_ESTOQUE'].isna() | (sem_estoque_df['QT_ESTOQUE'] <= 0)]

        # Renomear as colunas
        sem_estoque_df_renomeado = sem_estoque_df_renomeado.rename(columns={
            'CODPROD': 'CÓDIGO PRODUTO',
            'NOME_PRODUTO': 'NOME DO PRODUTO',
            'QT': 'QUANTIDADE VENDIDA',
            'QT_ESTOQUE': 'ESTOQUE TOTAL'
        })

        # Filtrar para remover linhas onde 'NOME DO PRODUTO' é NaN ou vazio
        sem_estoque_df_renomeado = sem_estoque_df_renomeado[
            sem_estoque_df_renomeado['NOME DO PRODUTO'].notna() & 
            (sem_estoque_df_renomeado['NOME DO PRODUTO'] != '')
        ]

        # Reordenar as colunas na ordem solicitada
        sem_estoque_df_renomeado = sem_estoque_df_renomeado[[
            'CÓDIGO PRODUTO', 'NOME DO PRODUTO', 'QUANTIDADE VENDIDA', 'ESTOQUE TOTAL'
        ]]

        # Configurar a tabela de produtos sem estoque com AgGrid e larguras fixas
        gb = GridOptionsBuilder.from_dataframe(sem_estoque_df_renomeado)
        gb.configure_default_column(editable=False, filter=True, sortable=True, resizable=False)
        # Definir larguras fixas para cada coluna
        gb.configure_column("CÓDIGO PRODUTO", width=150)
        gb.configure_column("NOME DO PRODUTO", width=300)
        gb.configure_column("QUANTIDADE VENDIDA", width=200)
        gb.configure_column("ESTOQUE TOTAL", width=200)
        gb.configure_pagination(enabled=False)
        gb.configure_grid_options(domLayout='normal')
        grid_options = gb.build()

        # Formatar números para exibição
        df_sem_estoque_display = sem_estoque_df_renomeado.copy()
        df_sem_estoque_display['QUANTIDADE VENDIDA'] = pd.to_numeric(df_sem_estoque_display['QUANTIDADE VENDIDA'], errors='coerce').fillna(0)
        df_sem_estoque_display['ESTOQUE TOTAL'] = pd.to_numeric(df_sem_estoque_display['ESTOQUE TOTAL'], errors='coerce').fillna(0)
        df_sem_estoque_display['QUANTIDADE VENDIDA'] = df_sem_estoque_display['QUANTIDADE VENDIDA'].apply(lambda x: f"{x:,.0f}")
        df_sem_estoque_display['ESTOQUE TOTAL'] = df_sem_estoque_display['ESTOQUE TOTAL'].apply(lambda x: f"{x:,.0f}")

        AgGrid(
            df_sem_estoque_display,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.NO_UPDATE,
            allow_unsafe_jscode=True,
            height=300,
            theme='streamlit',
            fit_columns_on_grid_load=True
        )

if __name__ == "__main__":
    main()