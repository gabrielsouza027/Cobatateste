import streamlit as st
import pandas as pd
import datetime
from cachetools import TTLCache
import requests
from dotenv import load_dotenv
import os

# Configuração da página
st.set_page_config(page_title="Pedidos de Venda", layout="wide")

# Carregar variáveis de ambiente
load_dotenv()

# Configuração do cache (TTL de 180 segundos)
cache = TTLCache(maxsize=1, ttl=180)

# Configuração do Supabase
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpvem9tbnBwd3B3Z3RxZGd0d255Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDY1NTYzMDYsImV4cCI6MjA2MjEzMjMwNn0.KcX5BOG-hiqo6baMinRuJjxmtgGKbWNZjNuzVLk9GiI")
SUPABASE_ENDPOINTS = [
    {
        "url": os.getenv("SUPABASE_URL_PCPEDI", "https://zozomnppwpwgtqdgtwny.supabase.co/rest/v1/PCPEDI?select=*"),
        "columns": ['NUMPED', 'NUMCAR', 'DATA', 'CODCLI', 'CLIENTE', 'CODIGO_VENDEDOR', 'NOME_VENDEDOR', 
                    'NUMNOTA', 'OBS', 'OBS1', 'OBS2', 'POSICAO', 'CODFILIAL', 
                    'CODPRACA', 'PRACA', 'MUNICIPIO', 'CODROTA', 'DESCRICAO_ROTA', 'QT', 
                    'PVENDA', 'CODPROD', 'DESCRICAO_PRODUTO']
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

# Função para buscar dados de múltiplos endpoints
@st.cache_data(show_spinner=False)
def fetch_pedidos(data_inicial, data_final):
    key = f"{data_inicial}_{data_final}"
    if key not in cache:
        try:
            # Formatar datas para a query
            data_inicial_str = data_inicial
            data_final_str = data_final
            
            # Lista para armazenar DataFrames de cada endpoint
            dfs = []
            
            # Iterar sobre os endpoints
            for endpoint in SUPABASE_ENDPOINTS:
                url = endpoint["url"]
                columns = endpoint["columns"]
                
                # Query com filtro de datas
                query_url = f"{url}&DATA=gte.{data_inicial_str}&DATA=lte.{data_final_str}"
                response = requests.get(query_url, headers=SUPABASE_HEADERS, timeout=30)
                response.raise_for_status()
                
                # Converter resposta para DataFrame
                data = response.json()
                if not data:
                    st.warning(f"Nenhum dado encontrado para o endpoint {url} entre {data_inicial} e {data_final}.")
                    continue
                
                df = pd.DataFrame(data)
                
                # Verificar se as colunas solicitadas existem
                missing_columns = [col for col in columns if col not in df.columns]
                if missing_columns:
                    st.error(f"Colunas não encontradas no endpoint {url}: {', '.join(missing_columns)}")
                    continue
                
                # Selecionar apenas as colunas especificadas
                df = df[columns]
                dfs.append(df)
            
            if not dfs:
                st.warning(f"Nenhum dado encontrado entre {data_inicial} e {data_final}.")
                cache[key] = pd.DataFrame()
                return cache[key]
            
            # Combinar DataFrames
            df_combined = dfs[0]
            for df in dfs[1:]:
                df_combined = pd.merge(df_combined, df, on=['NUMPED', 'DATA', 'CODPROD'], how='outer', suffixes=('', '_dup'))
                # Remover colunas duplicadas
                for col in df_combined.columns:
                    if col.endswith('_dup'):
                        df_combined.drop(columns=col, inplace=True)
            
            # Verificar colunas obrigatórias
            required_columns = ['NUMPED', 'NUMCAR', 'DATA', 'CODCLI', 'CLIENTE', 'CODIGO_VENDEDOR', 'NOME_VENDEDOR', 
                               'NUMNOTA', 'OBS', 'OBS1', 'OBS2', 'POSICAO', 'CODFILIAL', 
                               'CODPRACA', 'PRACA', 'MUNICIPIO', 'CODROTA', 'DESCRICAO_ROTA', 'QT', 
                               'PVENDA', 'CODPROD', 'DESCRICAO_PRODUTO']
            missing_columns = [col for col in required_columns if col not in df_combined.columns]
            if missing_columns:
                st.error(f"Colunas obrigatórias não encontradas nos dados combinados: {', '.join(missing_columns)}")
                cache[key] = pd.DataFrame()
                return cache[key]
            
            # Converter tipos
            df_combined['DATA'] = pd.to_datetime(df_combined['DATA'], errors='coerce')
            df_combined['QT'] = pd.to_numeric(df_combined['QT'], errors='coerce').fillna(0)
            df_combined['PVENDA'] = pd.to_numeric(df_combined['PVENDA'], errors='coerce').fillna(0)
            
            cache[key] = df_combined
        except (requests.exceptions.RequestException, ValueError) as e:
            st.error(f"Erro ao buscar dados do Supabase: {e}")
            cache[key] = pd.DataFrame()
        except Exception as e:
            st.error(f"Erro inesperado ao processar dados: {e}")
            cache[key] = pd.DataFrame()
    return cache[key]

# Função para mapear os valores de POSICAO e adicionar cor
def formatar_posicao(posicao):
    posicao_map = {
        'L': ('LIBERADO', '#008000'), 
        'M': ('MONTADO', '#FFA500'), 
        'F': ('FATURADO', '#0000FF'), 
        'C': ('CANCELADO', '#FF0000')
    }
    texto, cor = posicao_map.get(posicao, (posicao, '#000000'))
    return f'<span style="color:{cor}">{texto}</span>'

# Função principal do Streamlit
def main():
    st.title("Pedidos de Venda")

    # Inicializar session_state
    if 'pedidos_list' not in st.session_state:
        st.session_state.pedidos_list = []
    if 'display_limit' not in st.session_state:
        st.session_state.display_limit = 50
    if 'selected_filiais' not in st.session_state:
        st.session_state.selected_filiais = []
    if 'selected_rotas' not in st.session_state:
        st.session_state.selected_rotas = []

    # Seção de Filtros
    with st.container(border=True):
        st.markdown("### Filtros", unsafe_allow_html=True)

        # Período
        st.markdown("**📅 Período**", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            data_inicial = st.date_input("Data Inicial", datetime.date.today(), key="data_inicial")
        with col2:
            data_final = st.date_input("Data Final", datetime.date.today(), key="data_final")
        st.divider()

        if data_inicial > data_final:
            st.error("A data inicial não pode ser maior que a data final.")
            return

        # Pesquisa
        st.markdown("**🔍 Pesquisa**", unsafe_allow_html=True)
        col3, col4 = st.columns(2)
        with col3:
            search_client = st.text_input("Cliente ou Pedido", "", placeholder="Código, nome ou nº do pedido")
        with col4:
            search_seller = st.text_input("Vendedor", "", placeholder="Código ou nome do vendedor")
        st.divider()

    # Carregar os dados
    with st.spinner(f"Carregando pedidos entre {data_inicial} e {data_final}..."):
        df_pedidos = fetch_pedidos(data_inicial.strftime("%Y-%m-%d"), data_final.strftime("%Y-%m-%d"))

    if df_pedidos.empty:
        st.warning("Nenhum pedido encontrado ou erro ao carregar os dados.")
        return

    # Processar dados
    df_grouped = df_pedidos.groupby('NUMPED').agg({
        'NUMCAR': 'first', 'DATA': 'first', 'CODCLI': 'first', 'CLIENTE': 'first',
        'CODIGO_VENDEDOR': 'first', 'NOME_VENDEDOR': 'first', 'NUMNOTA': 'first', 'OBS': 'first',
        'OBS1': 'first', 'OBS2': 'first', 'POSICAO': 'first', 'CODFILIAL': 'first',
        'CODPRACA': 'first', 'PRACA': 'first', 'MUNICIPIO': 'first', 'CODROTA': 'first',
        'DESCRICAO_ROTA': 'first', 'QT': 'sum', 'PVENDA': 'mean'
    }).reset_index()

    df_grouped['valor_total'] = df_grouped['QT'] * df_grouped['PVENDA']
    pedidos_dict = df_grouped.to_dict('records')
    pedidos_list_full = pedidos_dict
    filiais_unicas = sorted(set(df_grouped['CODFILIAL'].dropna().astype(str)))
    rotas_unicas = sorted(set(df_grouped['DESCRICAO_ROTA'].dropna().astype(str)))

    # Filtros Avançados e Status
    with st.container(border=True):
        # Filtros Avançados - Filiais
        st.markdown("**🏢 Filiais**", unsafe_allow_html=True)
        col5, col6 = st.columns(2)
        with col5:
            for filial in filiais_unicas[:len(filiais_unicas)//2 + 1]:
                if st.checkbox(f"Filial {filial}", value=filial in st.session_state.selected_filiais, key=f"filial_{filial}"):
                    if filial not in st.session_state.selected_filiaisPOSIT:
                        st.session_state.selected_filiais.append(filial)
                else:
                    if filial in st.session_state.selected_filiais:
                        st.session_state.selected_filiais.remove(filial)
        with col6:
            for filial in filiais_unicas[len(filiais_unicas)//2 + 1:]:
                if st.checkbox(f"Filial {filial}", value=filial in st.session_state.selected_filiais, key=f"filial_{filial}"):
                    if filial not in st.session_state.selected_filiais:
                        st.session_state.selected_filiais.append(filial)
                else:
                    if filial in st.session_state.selected_filiais:
                        st.session_state.selected_filiais.remove(filial)
        if st.button("Selecionar Todas as Filiais", key="select_all_filial", use_container_width=True):
            st.session_state.selected_filiais = filiais_unicas.copy()
        st.divider()

        # Filtros Avançados - Rotas
        st.markdown("**🛤️ Rotas**", unsafe_allow_html=True)
        col7, col8 = st.columns(2)
        with col7:
            for rota in rotas_unicas[:len(rotas_unicas)//2 + 1]:
                if st.checkbox(f"{rota}", value=rota in st.session_state.selected_rotas, key=f"rota_{rota}"):
                    if rota not in st.session_state.selected_rotas:
                        st.session_state.selected_rotas.append(rota)
                else:
                    if rota in st.session_state.selected_rotas:
                        st.session_state.selected_rotas.remove(rota)
        with col8:
            for rota in rotas_unicas[len(rotas_unicas)//2 + 1:]:
                if st.checkbox(f"{rota}", value=rota in st.session_state.selected_rotas, key=f"rota_{rota}"):
                    if rota not in st.session_state.selected_rotas:
                        st.session_state.selected_rotas.append(rota)
                else:
                    if rota in st.session_state.selected_rotas:
                        st.session_state.selected_rotas.remove(rota)
        if st.button("Selecionar Todas as Rotas", key="select_all_rotas", use_container_width=True):
            st.session_state.selected_rotas = rotas_unicas.copy()
        st.divider()

        # Status
        st.markdown("**📊 Status**", unsafe_allow_html=True)
        col9, col10, col11, col12 = st.columns(4)
        with col9:
            show_liberado = st.checkbox("✅ Liberado", value=True, key="liberado")
        with col10:
            show_montado = st.checkbox("📦 Montado", value=True, key="montado")
        with col11:
            show_faturado = st.checkbox("💳 Faturado", value=True, key="faturado")
        with col12:
            show_cancelado = st.checkbox("❌ Cancelado", value=False, key="cancelado")
        st.divider()

        # Botão Aplicar Filtros
        if st.button("Aplicar Filtros", key="apply_filters", type="primary", use_container_width=True):
            pedidos_list = pedidos_list_full
            if search_client:
                pedidos_list = [p for p in pedidos_list if search_client.lower() in str(p.get("CODCLI", "")).lower() or 
                                search_client.lower() in str(p.get("CLIENTE", "")).lower() or 
                                search_client.lower() in str(p.get("NUMPED", "")).lower()]
            if search_seller:
                pedidos_list = [p for p in pedidos_list if search_seller.lower() in str(p.get("CODIGO_VENDEDOR", "")).lower() or 
                                search_seller.lower() in str(p.get("NOME_VENDEDOR", "")).lower()]
            if st.session_state.selected_filiais:
                pedidos_list = [p for p in pedidos_list if str(p.get("CODFILIAL", "")) in st.session_state.selected_filiais]
            if st.session_state.selected_rotas:
                pedidos_list = [p for p in pedidos_list if str(p.get("DESCRICAO_ROTA", "")) in st.session_state.selected_rotas]
            if not (show_liberado and show_montado and show_faturado and show_cancelado):
                selected_positions = []
                if show_liberado: selected_positions.append('L')
                if show_montado: selected_positions.append('M')
                if show_faturado: selected_positions.append('F')
                if show_cancelado: selected_positions.append('C')
                if selected_positions:
                    pedidos_list = [p for p in pedidos_list if str(p.get("POSICAO", "")) in selected_positions]
            if not pedidos_list:
                st.warning("Nenhum pedido encontrado com os critérios de pesquisa.")
                st.session_state.pedidos_list = []
            else:
                st.session_state.pedidos_list = pedidos_list
            st.session_state.display_limit = 50

    # Exibir pedidos
    if st.session_state.pedidos_list:
        st.header("Lista de Pedidos", divider="gray")
        st.write(f"Total de pedidos exibidos: {len(st.session_state.pedidos_list)} (Mostrando até {st.session_state.display_limit} de {len(st.session_state.pedidos_list)})")
        
        for pedido in st.session_state.pedidos_list[:st.session_state.display_limit]:
            with st.expander(f"Pedido {pedido.get('NUMPED', 'N/A')} - Cliente: {pedido.get('CLIENTE', 'N/A')} ({pedido.get('DESCRICAO_ROTA', 'N/A')} - {pedido.get('MUNICIPIO', 'N/A')})"):
                col5, col6 = st.columns(2)
                with col5:
                    st.markdown(f"""
                        **Nº Pedido:** {pedido.get('NUMPED', 'N/A')}  
                        **Nº Carregamento:** {pedido.get('NUMCAR', 'N/A')}  
                        **Data:** {pedido.get('DATA', 'N/A')}  
                        **Cód. Cliente:** {pedido.get('CODCLI', 'N/A')}  
                        **Cliente:** {pedido.get('CLIENTE', 'N/A')}  
                        **Rota:** {pedido.get('DESCRICAO_ROTA', 'N/A')}  
                        **Cidade:** {pedido.get('MUNICIPIO', 'N/A')}  
                        **Posição:** {formatar_posicao(pedido.get('POSICAO', ''))}  
                    """, unsafe_allow_html=True)
                with col6:
                    st.markdown(f"""
                        **Cód. Vendedor:** {pedido.get('CODIGO_VENDEDOR', 'N/A')}  
                        **Vendedor:** {pedido.get('NOME_VENDEDOR', 'N/A')}  
                        **Nº Nota:** {pedido.get('NUMNOTA', 'N/A')}  
                        **Cód. Filial:** {pedido.get('CODFILIAL', 'N/A')}  
                        **Observação:** {pedido.get('OBS', 'N/A')}  
                        **Observação 1:** {pedido.get('OBS1', 'N/A')}  
                        **Observação 2:** {pedido.get('OBS2', 'N/A')}  
                        **Valor Total:** R$ {pedido.get('valor_total', 0):.2f}
                    """, unsafe_allow_html=True)
                st.subheader("Produtos")
                produtos_df = df_pedidos[df_pedidos['NUMPED'] == pedido.get('NUMPED', '')][['CODPROD', 'DESCRICAO_PRODUTO', 'QT', 'PVENDA', 'POSICAO']]
                produtos_df["VALOR_TOTAL_ITEM"] = produtos_df["QT"] * produtos_df["PVENDA"]
                produtos_df = produtos_df.rename(columns={
                    "CODPROD": "Código Produto", "DESCRICAO_PRODUTO": "Descrição", "QT": "Quantidade",
                    "PVENDA": "Preço Unitário", "VALOR_TOTAL_ITEM": "Valor Total", "POSICAO": "Posição"
                })
                if not produtos_df.empty:
                    styled_df = produtos_df.style.format({
                        "Preço Unitário": "R$ {:.2f}", "Valor Total": "R$ {:.2f}", "Quantidade": "{:.0f}"
                    }).set_properties(**{
                        'text-align': 'center', 'font-size': '12pt', 'border': '1px solid #ddd', 'padding': '5px'
                    }).set_table_styles([
                        {'selector': 'th', 'props': [('background-color', '#f4f4f4'), ('font-weight', 'bold'),
                                                    ('text-align', 'center'), ('border', '1px solid #ddd'), ('padding', '5px')]}
                    ]).hide(axis="index")
                    st.dataframe(styled_df, height=300, use_container_width=True)
                else:
                    st.info("Nenhum produto encontrado para este pedido.")

        if st.session_state.display_limit < len(st.session_state.pedidos_list):
            st.button("Carregar Mais", key="load_more", on_click=lambda: st.session_state.update(display_limit=st.session_state.display_limit + 50))
    else:
        st.info("Nenhum pedido disponível para exibição. Aplique os filtros para carregar os dados.")

if __name__ == "__main__":
    main()