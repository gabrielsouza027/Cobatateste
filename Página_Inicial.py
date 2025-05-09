import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import locale
import plotly.express as px
from cachetools import TTLCache
import os

# Configuração da página
st.set_page_config(page_title="Dashboard de Faturamento", layout="wide")

# Tentar definir o locale para formatação monetária
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    st.warning("Locale 'pt_BR.UTF-8' não disponível. Usando formatação padrão.")
    locale.setlocale(locale.LC_ALL, '')

# Configuração do cache (TTL de 180 segundos)
cache = TTLCache(maxsize=1, ttl=180)

# Configuração do cliente Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zozomnppwpwgtqdgtwny.supabase.co/rest/v1/PCPEDC?select=*")
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

# Função para obter dados do endpoint Supabase com cache e paginação
@st.cache_data(show_spinner=False)
def carregar_dados():
    cache_key = SUPABASE_URL
    if cache_key in cache:
        return cache[cache_key]

    all_data = []
    page_size = 1000
    start = 0
    headers = SUPABASE_HEADERS.copy()

    try:
        while True:
            headers["Range"] = f"{start}-{start + page_size - 1}"
            response = requests.get(SUPABASE_URL, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            if not data or len(data) < page_size:  # Parar se não houver mais dados
                all_data.extend(data)
                break
            all_data.extend(data)
            start += page_size

        if all_data:
            df = pd.DataFrame(all_data)
            required_columns = ['PVENDA', 'QT', 'CODFILIAL', 'DATA_PEDIDO', 'NUMPED']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                st.error(f"Colunas ausentes nos dados retornados pela API: {missing_columns}")
                cache[cache_key] = pd.DataFrame()
                return pd.DataFrame()
            
            # Converter DATA_PEDIDO para datetime
            df['DATA_PEDIDO'] = pd.to_datetime(df['DATA_PEDIDO'], errors='coerce')
            df = df.dropna(subset=['DATA_PEDIDO'])  # Remover linhas com DATA_PEDIDO inválida
            
            # Calcular VLTOTAL como PVENDA * QT
            df['PVENDA'] = pd.to_numeric(df['PVENDA'], errors='coerce').fillna(0)
            df['QT'] = pd.to_numeric(df['QT'], errors='coerce').fillna(0)
            df['VLTOTAL'] = df['PVENDA'] * df['QT']
            df['VLTOTAL'] = df['VLTOTAL'].fillna(0)
            
            # Filtrar apenas filiais 1 e 2
            df = df[df['CODFILIAL'].isin(['1', '2'])]
            cache[cache_key] = df
        else:
            st.warning("Nenhum dado retornado pela API.")
            cache[cache_key] = pd.DataFrame()
            df = pd.DataFrame()

    except (requests.exceptions.RequestException, ValueError) as e:
        st.error(f"Erro ao buscar dados da API: {e}")
        cache[cache_key] = pd.DataFrame()
        df = pd.DataFrame()

    return cache[cache_key]

def calcular_faturamento(data, hoje, ontem, semana_inicial, semana_passada_inicial):
    faturamento_hoje = data[data['DATA_PEDIDO'].dt.date == hoje.date()]['VLTOTAL'].sum()
    faturamento_ontem = data[data['DATA_PEDIDO'].dt.date == ontem.date()]['VLTOTAL'].sum()
    faturamento_semanal_atual = data[(data['DATA_PEDIDO'].dt.date >= semana_inicial.date()) & (data['DATA_PEDIDO'].dt.date <= hoje.date())]['VLTOTAL'].sum()
    faturamento_semanal_passada = data[(data['DATA_PEDIDO'].dt.date >= semana_passada_inicial.date()) & (data['DATA_PEDIDO'].dt.date < semana_inicial.date())]['VLTOTAL'].sum()
    return faturamento_hoje, faturamento_ontem, faturamento_semanal_atual, faturamento_semanal_passada

def calcular_quantidade_pedidos(data, hoje, ontem, semana_inicial, semana_passada_inicial):
    pedidos_hoje = data[data['DATA_PEDIDO'].dt.date == hoje.date()]['NUMPED'].nunique()
    pedidos_ontem = data[data['DATA_PEDIDO'].dt.date == ontem.date()]['NUMPED'].nunique()
    pedidos_semanal_atual = data[(data['DATA_PEDIDO'].dt.date >= semana_inicial.date()) & (data['DATA_PEDIDO'].dt.date <= hoje.date())]['NUMPED'].nunique()
    pedidos_semanal_passada = data[(data['DATA_PEDIDO'].dt.date >= semana_passada_inicial.date()) & (data['DATA_PEDIDO'].dt.date < semana_inicial.date())]['NUMPED'].nunique()
    return pedidos_hoje, pedidos_ontem, pedidos_semanal_atual, pedidos_semanal_passada

def calcular_comparativos(data, hoje, mes_atual, ano_atual):
    mes_anterior = mes_atual - 1 if mes_atual > 1 else 12
    ano_anterior = ano_atual if mes_atual > 1 else ano_atual - 1
    faturamento_mes_atual = data[(data['DATA_PEDIDO'].dt.month == mes_atual) & (data['DATA_PEDIDO'].dt.year == ano_atual)]['VLTOTAL'].sum()
    pedidos_mes_atual = data[(data['DATA_PEDIDO'].dt.month == mes_atual) & (data['DATA_PEDIDO'].dt.year == ano_atual)]['NUMPED'].nunique()
    faturamento_mes_anterior = data[(data['DATA_PEDIDO'].dt.month == mes_anterior) & (data['DATA_PEDIDO'].dt.year == ano_anterior)]['VLTOTAL'].sum()
    pedidos_mes_anterior = data[(data['DATA_PEDIDO'].dt.month == mes_anterior) & (data['DATA_PEDIDO'].dt.year == ano_anterior)]['NUMPED'].nunique()
    return faturamento_mes_atual, faturamento_mes_anterior, pedidos_mes_atual, pedidos_mes_anterior

def formatar_valor(valor):
    try:
        return locale.currency(valor, grouping=True, symbol=True)
    except:
        return f"R$ {valor:,.2f}"

def main():
    st.markdown("""
    <style>
        .st-emotion-cache-1ibsh2c {
            width: 100%;
            padding: 0rem 1rem 0rem;
            max-width: initial;
            min-width: auto;
        }
        .st-column {
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .card-container {
            display: flex;
            align-items: center;
            background-color: #302d2d;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 10px;
            color: white;
            flex-direction: column;
            text-align: center;
            min-width: 180px;
            height: 160px;
        }
        .card-container img {
            width: 51px;
            height: 54px;
            margin-bottom: 5px;
        }
        .number {
            font-size: 20px;
            font-weight: bold;
            margin-top: 5px;
        }
    </style>
    """, unsafe_allow_html=True)

    st.title('Dashboard de Faturamento')
    st.markdown("### Resumo de Vendas")

    # Carregar dados com cache
    with st.spinner("Carregando dados..."):
        data = carregar_dados()
    
    if not data.empty:
        col1, col2 = st.columns(2)
        with col1:
            filial_1 = st.checkbox("Filial 1", value=True)
        with col2:
            filial_2 = st.checkbox("Filial 2", value=True)

        # Definir filiais selecionadas
        filiais_selecionadas = []
        if filial_1:
            filiais_selecionadas.append('1')
        if filial_2:
            filiais_selecionadas.append('2')

        # Verificar se pelo menos uma filial está selecionada
        if not filiais_selecionadas:
            st.warning("Por favor, selecione pelo menos uma filial para exibir os dados.")
            return

        # Filtrar dados com base nas filiais selecionadas
        data_filtrada = data[data['CODFILIAL'].isin(filiais_selecionadas)]

        hoje = pd.to_datetime('today').normalize()
        ontem = hoje - timedelta(days=1)
        semana_inicial = hoje - timedelta(days=hoje.weekday())
        semana_passada_inicial = semana_inicial - timedelta(days=7)

        faturamento_hoje, faturamento_ontem, faturamento_semanal_atual, faturamento_semanal_passada = calcular_faturamento(data_filtrada, hoje, ontem, semana_inicial, semana_passada_inicial)
        pedidos_hoje, pedidos_ontem, pedidos_semanal_atual, pedidos_semanal_passada = calcular_quantidade_pedidos(data_filtrada, hoje, ontem, semana_inicial, semana_passada_inicial)

        mes_atual = hoje.month
        ano_atual = hoje.year
        faturamento_mes_atual, faturamento_mes_anterior, pedidos_mes_atual, pedidos_mes_anterior = calcular_comparativos(data_filtrada, hoje, mes_atual, ano_atual)

        col1, col2, col3, col4, col5 = st.columns(5)

        def calcular_variacao(atual, anterior):
            if anterior == 0:
                return 100 if atual > 0 else 0
            return ((atual - anterior) / anterior) * 100
        
        def icone_variacao(valor):
            if valor > 0:
                return f"<span style='color: green;'>▲ {valor:.2f}%</span>"
            elif valor < 0:
                return f"<span style='color: red;'>▼ {valor:.2f}%</span>"
            else:
                return "0%"

        var_faturamento_mes = calcular_variacao(faturamento_mes_atual, faturamento_mes_anterior)
        var_pedidos_mes = calcular_variacao(pedidos_mes_atual, pedidos_mes_anterior)
        var_faturamento_hoje = calcular_variacao(faturamento_hoje, faturamento_ontem)
        var_pedidos_hoje = calcular_variacao(pedidos_hoje, pedidos_ontem)
        var_faturamento_semananterior = calcular_variacao(faturamento_semanal_atual, faturamento_semanal_passada)

        def grafico_pizza_variacao(labels, valores, titulo):
            valores = [abs(v) for v in valores]  # Evitar valores negativos no gráfico de pizza
            fig = px.pie(
                names=labels,
                values=valores,
                title=titulo,
                hole=0.4,
                color=labels,
                color_discrete_map={"Mês Atual": "green", "Mês Anterior": "red", "Hoje": "green", "Ontem": "red",
                                    "Semana Atual": "green", "Semana Passada": "red",
                                    "Pedidos Mês Atual": "green", "Pedidos Mês Passado": "red",
                                    "Pedidos Hoje": "green", "Pedidos Ontem": "red"}
            )
            fig.update_layout(margin=dict(t=30, b=30, l=30, r=30))
            return fig

        with col1:
            st.markdown(f"""
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/2460/2460494.png" alt="Ícone Hoje">
                    <span>Hoje:</span> 
                    <div class="number">{formatar_valor(faturamento_hoje)}</div>
                    <small>Variação: {icone_variacao(var_faturamento_hoje)}</small>
                </div>
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/3703/3703896.png" alt="Ícone Ontem">
                    <span>Ontem:</span> 
                    <div class="number">{formatar_valor(faturamento_ontem)}</div>
                </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/4435/4435153.png" alt="Ícone Semana Atual">
                    <span>Semana Atual:</span> 
                    <div class="number">{formatar_valor(faturamento_semanal_atual)}</div>
                    <small>Variação: {icone_variacao(var_faturamento_semananterior)}</small>
                </div>
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/4435/4435153.png" alt="Ícone Semana Passada">
                    <span>Semana Passada:</span> 
                    <div class="number">{formatar_valor(faturamento_semanal_passada)}</div>
                </div>
            """, unsafe_allow_html=True)

        with col3:
            st.markdown(f"""
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/10535/10535844.png" alt="Ícone Mês Atual">
                    <span>Mês Atual:</span> 
                    <div class="number">{formatar_valor(faturamento_mes_atual)}</div>
                    <small>Variação: {icone_variacao(var_faturamento_mes)}</small>
                </div>
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/584/584052.png" alt="Ícone Mês Anterior">
                    <span>Mês Anterior:</span> 
                    <div class="number">{formatar_valor(faturamento_mes_anterior)}</div>
                </div>
            """, unsafe_allow_html=True)

        with col4:
            st.markdown(f"""
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/6632/6632848.png" alt="Ícone Pedidos Mês Atual">
                    <span>Pedidos Mês Atual:</span> 
                    <div class="number">{pedidos_mes_atual}</div>
                    <small>Variação: {icone_variacao(var_pedidos_mes)}</small>
                </div>
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/925/925049.png" alt="Ícone Pedidos Mês Anterior">
                    <span>Pedidos Mês Anterior:</span> 
                    <div class="number">{pedidos_mes_anterior}</div>
                </div>
            """, unsafe_allow_html=True)

        with col5:
            st.markdown(f"""
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/14018/14018701.png" alt="Ícone Pedidos Hoje">
                    <span>Pedidos Hoje:</span> 
                    <div class="number">{pedidos_hoje}</div>
                    <small>Variação: {icone_variacao(var_pedidos_hoje)}</small>
                </div>
                <div class="card-container">
                    <img src="https://cdn-icons-png.flaticon.com/512/5220/5220625.png" alt="Ícone Pedidos Ontem">
                    <span>Pedidos Ontem:</span> 
                    <div class="number">{pedidos_ontem}</div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("---")

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.plotly_chart(grafico_pizza_variacao(["Hoje", "Ontem"], [faturamento_hoje, faturamento_ontem], "Variação de Faturamento (Hoje x Ontem)"), use_container_width=True)
        with col2:
            st.plotly_chart(grafico_pizza_variacao(["Semana Atual", "Semana Passada"], [faturamento_semanal_atual, faturamento_semanal_passada], "Variação de Faturamento (Semana)"), use_container_width=True)
        with col3:
            st.plotly_chart(grafico_pizza_variacao(["Mês Atual", "Mês Anterior"], [faturamento_mes_atual, faturamento_mes_anterior], "Variação de Faturamento (Mês)"), use_container_width=True)
        with col4:
            st.plotly_chart(grafico_pizza_variacao(["Pedidos Mês Atual", "Pedidos Mês Passado"], [pedidos_mes_atual, pedidos_mes_anterior], "Variação de Pedidos (Mês)"), use_container_width=True)
        with col5:
            st.plotly_chart(grafico_pizza_variacao(["Pedidos Hoje", "Pedidos Ontem"], [pedidos_hoje, pedidos_ontem], "Variação de Pedidos (Hoje x Ontem)"), use_container_width=True)

        # Gráfico de linhas com seletores de data
        st.markdown("---")
        st.subheader("Comparação de Vendas por Mês e Ano")

        # Seletores de data
        col_data1, col_data2 = st.columns(2)
        min_date = data_filtrada['DATA_PEDIDO'].min() if not data_filtrada.empty else pd.to_datetime("2024-01-01")
        max_date = data_filtrada['DATA_PEDIDO'].max() if not data_filtrada.empty else pd.to_datetime("today")
        with col_data1:
            data_inicial = st.date_input("Data Inicial", value=pd.to_datetime("2024-04-08"), min_value=min_date, max_value=max_date)
        with col_data2:
            data_final = st.date_input("Data Final", value=max_date, min_value=min_date, max_value=max_date)

        if data_inicial > data_final:
            st.error("A data inicial não pode ser maior que a data final.")
            return

        # Filtrar dados pelo período selecionado
        df_periodo = data_filtrada[(data_filtrada['DATA_PEDIDO'].dt.date >= data_inicial) & 
                                   (data_filtrada['DATA_PEDIDO'].dt.date <= data_final)].copy()

        if not df_periodo.empty:
            # Adicionar colunas de ano e mês
            df_periodo['Ano'] = df_periodo['DATA_PEDIDO'].dt.year
            df_periodo['Mês'] = df_periodo['DATA_PEDIDO'].dt.month

            # Agrupar por ano e mês
            vendas_por_mes_ano = df_periodo.groupby(['Ano', 'Mês']).agg(
                Valor_Total_Vendido=('VLTOTAL', 'sum')
            ).reset_index()

            # Criar gráfico de linhas com uma linha por ano
            fig = px.line(vendas_por_mes_ano, x='Mês', y='Valor_Total_Vendido', color='Ano',
                          title=f'Vendas por Mês ({data_inicial} a {data_final})',
                          labels={'Mês': 'Mês', 'Valor_Total_Vendido': 'Valor Total Vendido (R$)', 'Ano': 'Ano'},
                          markers=True)

            # Ajustes visuais
            fig.update_layout(
                title_font_size=20,
                xaxis_title_font_size=16,
                yaxis_title_font_size=16,
                xaxis_tickfont_size=14,
                yaxis_tickfont_size=14,
                xaxis_tickangle=-45,
                xaxis=dict(tickmode='array', tickvals=list(range(1, 13)), ticktext=['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'])
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Nenhum dado disponível para o período selecionado.")
    else:
        st.warning("Nenhum dado disponível para exibição.")

if __name__ == "__main__":
    main()