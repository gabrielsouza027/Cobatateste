import streamlit as st
import pandas as pd
from datetime import datetime
from cachetools import TTLCache
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import requests
import os

# Configuração da página
st.set_page_config(page_title="Dashboard de Vendas", layout="wide")

# Injetar CSS para garantir que o AgGrid ocupe toda a largura
st.markdown("""
    <style>
    .ag-root-wrapper {
        width: 100% !important;
        max-width: 100% !important;
    }
    .ag-theme-streamlit {
        width: 100% !important;
    }
    .stApp {
        max-width: 100% !important;
    }
    </style>
""", unsafe_allow_html=True)

# Configuração do cliente Supabase (usando API REST diretamente)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zozomnppwpwgtqdgtwny.supabase.co/rest/v1/PCVENDEDOR2?select=*")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpvem9tbnBwd3B3Z3RxZGd0d255Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDY1NTYzMDYsImV4cCI6MjA2MjEzMjMwNn0.KcX5BOG-hiqo6baMinRuJjxmtgGKbWNZjNuzVLk9GiI")
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Validar URL e chave
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Erro: SUPABASE_URL ou SUPABASE_KEY não estão definidos.")
    st.stop()

# Testar conexão com uma query simples
try:
    response = requests.get(SUPABASE_URL, headers=SUPABASE_HEADERS, timeout=10)
    response.raise_for_status()
except Exception as e:
    st.error(f"Erro ao conectar ao Supabase: {e}")
    st.stop()

# Configuração do cache (TTL de 180 segundos)
cache = TTLCache(maxsize=1, ttl=180)

# Função para buscar dados da tabela PCVENDEDOR2 com cache
@st.cache_data(show_spinner=False)
def get_data_from_endpoint(data_inicial, data_final):
    key = f"{data_inicial.strftime('%Y-%m-%d')}_{data_final.strftime('%Y-%m-%d')}"
    if key not in cache:
        try:
            # Formatar datas para a query
            data_inicial_str = data_inicial.strftime('%Y-%m-%d')
            data_final_str = data_final.strftime('%Y-%m-%d')
            
            # Query com filtro de datas
            query_url = f"{SUPABASE_URL}&DATA=gte.{data_inicial_str}&DATA=lte.{data_final_str}"
            response = requests.get(query_url, headers=SUPABASE_HEADERS, timeout=30)
            response.raise_for_status()
            
            # Converter resposta para DataFrame
            data = response.json()
            if not data:
                st.warning("Nenhum dado encontrado para o período selecionado.")
                cache[key] = pd.DataFrame()
                return cache[key]
            
            df = pd.DataFrame(data)
            
            # Verificar colunas obrigatórias
            required_columns = ['DATA', 'QT', 'PVENDA', 'FORNECEDOR', 'VENDEDOR', 'CLIENTE', 'PRODUTO', 'CODPROD', 'CODIGOVENDEDOR', 'CODCLI']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                st.error(f"Colunas ausentes nos dados retornados: {missing_columns}")
                cache[key] = pd.DataFrame()
                return cache[key]
            
            # Converter DATA para datetime e extrair mês e ano
            df['DATA'] = pd.to_datetime(df['DATA'], errors='coerce')
            df['MES'] = df['DATA'].dt.month
            df['ANO'] = df['DATA'].dt.year
            
            # Calcular valor total: quantidade × preço unitário
            df['QT'] = pd.to_numeric(df['QT'], errors='coerce').fillna(0)
            df['PVENDA'] = pd.to_numeric(df['PVENDA'], errors='coerce').fillna(0)
            df['VALOR_TOTAL_ITEM'] = df['QT'] * df['PVENDA']
            
            cache[key] = df
        except (requests.exceptions.RequestException, ValueError) as e:
            st.error(f"Erro ao buscar dados do Supabase: {e}")
            cache[key] = pd.DataFrame()
        except Exception as e:
            st.error(f"Erro inesperado ao processar dados: {e}")
            cache[key] = pd.DataFrame()
    return cache[key]

def main():
    st.title("Dashboard de Vendas")
    
    # Filtro de Data para Tabela 1
    st.subheader("Filtro de Período (Fornecedores)")
    today = datetime.today()
    col1, col2 = st.columns(2)
    with col1:
        data_inicial = st.date_input(
            "Data Inicial",
            value=datetime(today.year - 1, 1, 1),  # Um ano antes do dia atual
            key="data_inicial"
        )
    with col2:
        data_final = st.date_input(
            "Data Final",
            value=today,  # Dia atual
            key="data_final"
        )
    
    # Converter para datetime
    data_inicial = datetime.combine(data_inicial, datetime.min.time())
    data_final = datetime.combine(data_final, datetime.max.time())
    
    if data_inicial > data_final:
        st.error("A data inicial não pode ser maior que a data final.")
        return

    # Buscar dados para o período
    with st.spinner("Carregando dados..."):
        df = get_data_from_endpoint(data_inicial, data_final)
    
    if not df.empty:
        # --- Primeira Tabela: Valor Total por Fornecedor por Mês ---
        st.subheader("Valor Total por Fornecedor por Mês")
        
        # Barra de Pesquisa
        search_term = st.text_input("Pesquisar Fornecedor:", "", key="search_fornecedor")
        
        # Agrupar por fornecedor, mês e ano, calculando a soma de VALOR_TOTAL_ITEM
        df_grouped = df.groupby(['FORNECEDOR', 'MES', 'ANO'])['VALOR_TOTAL_ITEM'].sum().reset_index()
        
        # Tabela dinâmica para fornecedores como linhas e meses como colunas
        pivot_df = df_grouped.pivot_table(
            values='VALOR_TOTAL_ITEM',
            index='FORNECEDOR',
            columns=['ANO', 'MES'],
            aggfunc='sum',
            fill_value=0
        )
        
        # Renomear colunas para incluir ano e nome do mês
        month_names = {
            1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr',
            5: 'Mai', 6: 'Jun', 7: 'Jul', 8: 'Ago',
            9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'
        }
        new_columns = [
            f"{month_names[month]}-{year}" 
            for year, month in pivot_df.columns
        ]
        pivot_df.columns = new_columns
        
        # Adicionar coluna de total
        pivot_df['Total'] = pivot_df.sum(axis=1)
        
        # Resetar índice para tornar FORNECEDOR uma coluna
        pivot_df = pivot_df.reset_index()
        
        # Filtrar fornecedores com base na busca
        if search_term:
            pivot_df = pivot_df[
                pivot_df['FORNECEDOR'].str.contains(search_term, case=False, na=False)
            ]
        
        # Verificar se há resultados após o filtro
        if pivot_df.empty:
            st.warning("Nenhum fornecedor encontrado com o termo pesquisado.")
        else:
            # Configurar opções do AgGrid
            gb = GridOptionsBuilder.from_dataframe(pivot_df)
            gb.configure_default_column(
                sortable=True, filter=True, resizable=True, minWidth=100
            )
            gb.configure_column(
                "FORNECEDOR",
                headerName="Fornecedor",
                pinned="left",
                minWidth=200,
                filter="agTextColumnFilter"
            )
            for col in pivot_df.columns:
                if col != "FORNECEDOR":
                    gb.configure_column(
                        col,
                        headerName=col,
                        type=["numericColumn"],
                        valueFormatter="x.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'})",
                        minWidth=120
                    )
            
            # Configurações para ajuste dinâmico da largura
            gb.configure_grid_options(
                autoSizeStrategy={'type': 'fitGridWidth', 'defaultMinWidth': 100},
                enableRangeSelection=True,
                domLayout='normal'
            )
            
            # Renderizar AgGrid
            AgGrid(
                pivot_df,
                gridOptions=gb.build(),
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                height=400,
                allow_unsafe_jscode=True,
                theme="streamlit"
            )
            
            # Download CSV
            csv = pivot_df.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
            st.download_button(
                label="Download CSV - Fornecedores",
                data=csv,
                file_name=f'valor_vendas_por_fornecedor_{data_inicial.year}_ate_{data_final.strftime("%Y%m%d")}.csv',
                mime='text/csv'
            )
        
        # --- Segunda Tabela: Quantidade Vendida por Produto por Mês ---
        st.markdown("---")
        st.subheader("Quantidade Vendida por Produto por Mês")
        
        # Filtro de Ano e Mês
        anos = sorted(df['ANO'].unique())
        meses = sorted(df['MES'].unique())
        meses_nomes = [month_names[m] for m in meses]
        
        # Definir padrões para ano e mês (atual)
        current_year = today.year
        current_month = today.month
        current_month_name = month_names.get(current_month, 'Mai')
        
        # Seletor de Ano e Mês
        col1, col2 = st.columns(2)
        with col1:
            selected_ano = st.selectbox("Selecione o Ano", anos, index=anos.index(current_year) if current_year in anos else 0, key="ano_produto")
        with col2:
            selected_mes = st.selectbox("Selecione o Mês", meses_nomes, index=meses_nomes.index(current_month_name) if current_month_name in meses_nomes else 0, key="mes_produto")
        
        # Converter nome do mês de volta para número
        selected_mes_num = list(month_names.keys())[list(month_names.values()).index(selected_mes)]
        
        # Filtrar os dados com base no ano e mês selecionados
        df_filtered = df[
            (df['MES'] == selected_mes_num) & (df['ANO'] == selected_ano)
        ]
        
        if not df_filtered.empty:
            # Agrupar por colunas otimizadas
            pivot_produtos = df_filtered.groupby(
                ['CODPROD', 'PRODUTO', 'CODIGOVENDEDOR', 'VENDEDOR', 'CODCLI', 'CLIENTE', 'FORNECEDOR']
            )['QT'].sum().reset_index()
            
            # Reorganizar colunas para melhor apresentação
            pivot_produtos = pivot_produtos[
                ['PRODUTO', 'CODPROD', 'VENDEDOR', 'CODIGOVENDEDOR', 'CLIENTE', 'CODCLI', 'FORNECEDOR', 'QT']
            ]
            
            # Configurar AgGrid para exibir colunas de forma otimizada
            gb_produtos = GridOptionsBuilder.from_dataframe(pivot_produtos)
            gb_produtos.configure_default_column(
                sortable=True, filter=True, resizable=True, minWidth=100
            )
            gb_produtos.configure_column(
                "PRODUTO",
                headerName="Produto",
                pinned="left",
                minWidth=200,
                filter="agTextColumnFilter"
            )
            gb_produtos.configure_column(
                "CODPROD",
                headerName="Cód. Produto",
                minWidth=120,
                filter="agTextColumnFilter"
            )
            gb_produtos.configure_column(
                "VENDEDOR",
                headerName="Vendedor",
                minWidth=150,
                filter="agTextColumnFilter"
            )
            gb_produtos.configure_column(
                "CODIGOVENDEDOR",
                headerName="Cód. Vendedor",
                minWidth=120,
                filter="agTextColumnFilter"
            )
            gb_produtos.configure_column(
                "CLIENTE",
                headerName="Cliente",
                minWidth=150,
                filter="agTextColumnFilter"
            )
            gb_produtos.configure_column(
                "CODCLI",
                headerName="Cód. Cliente",
                minWidth=120,
                filter="agTextColumnFilter"
            )
            gb_produtos.configure_column(
                "FORNECEDOR",
                headerName="Fornecedor",
                minWidth=150,
                filter="agTextColumnFilter"
            )
            gb_produtos.configure_column(
                "QT",
                headerName="Quantidade",
                type=["numericColumn"],
                valueFormatter="Math.floor(x).toLocaleString('pt-BR')",
                minWidth=120
            )
            
            # Configurações para ajuste dinâmico da largura
            gb_produtos.configure_grid_options(
                autoSizeStrategy={'type': 'fitGridWidth', 'defaultMinWidth': 100},
                enableRangeSelection=True,
                domLayout='normal'
            )
            
            # Exibir tabela
            st.write(f"Quantidade vendida por produto para {selected_mes}-{selected_ano}:")
            AgGrid(
                pivot_produtos,
                gridOptions=gb_produtos.build(),
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                height=400,
                allow_unsafe_jscode=True,
                theme="streamlit"
            )
            
            # Exportar para CSV
            csv_produtos = pivot_produtos.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
            st.download_button(
                label="Download CSV - Produtos",
                data=csv_produtos,
                file_name=f'quantidade_vendida_por_produto_{selected_ano}_{selected_mes_num:02d}.csv',
                mime='text/csv'
            )
        else:
            st.warning("Nenhum dado encontrado para o mês e ano selecionados.")
    else:
        st.warning("Nenhum dado encontrado para o período selecionado.")

if __name__ == "__main__":
    main()