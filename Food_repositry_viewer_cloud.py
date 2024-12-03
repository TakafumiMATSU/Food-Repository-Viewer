import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
import requests

# Streamlitの設定
st.set_page_config(
    page_title="Food Repository Viewer",
    layout="wide"
)

# タイトルと説明文を表示
st.title("Food Repository Viewer")
st.markdown("""
本プログラムは食品レポジトリ ([https://metabolites.in/foods/](https://metabolites.in/foods/)) からAPIを介して情報取得しています。  
詳細情報は食品レポジトリ上で確認してください。
""")

# サンプルリストのCSVファイルパス
sample_list_file = "sample_list.csv"

# 初期化：セッションステートで選択状態を保持
if "selected_fids" not in st.session_state:
    st.session_state["selected_fids"] = set()  # 選択されたfidの集合

if "detection_mode" not in st.session_state:
    st.session_state["detection_mode"] = "pos"

# サンプルリストを読み込む
try:
    sample_list_df = pd.read_csv(sample_list_file)

    # 表示する列を設定（fid, nameJa, catJaを表示）
    display_columns = ['fid', 'nameJa', 'catJa']

    # サイドバーでRTのマージング幅を指定
    st.sidebar.header("RTマージングの設定")
    rt_merge_width = st.sidebar.slider("RTマージング幅 (min)", 0.05, 1.0, 0.2, step=0.05)

    # テーブルを表示（チェックボックスを含む）
    st.header("サンプルリスト（選択可能）")

    # チェックボックス列を作成
    if "選択" not in sample_list_df.columns:
        sample_list_df["選択"] = sample_list_df["fid"].apply(
            lambda x: x in st.session_state["selected_fids"]
        )

    # 選択状態を保持するためのフィードバックループを回避
    with st.form("table_form"):
        edited_df = st.data_editor(
            sample_list_df[display_columns + ['選択']],
            use_container_width=True,
            hide_index=True
        )
        submit_button = st.form_submit_button("保存")

    # 選択されたfidを更新
    if submit_button:
        selected_fids = edited_df[edited_df['選択']]['fid'].tolist()
        st.session_state["selected_fids"] = set(selected_fids)

    # 検出モードの選択（セッションステートで保持）
    detection_mode = st.sidebar.radio(
        "検出モードを選択",
        ["pos", "neg"],
        index=["pos", "neg"].index(st.session_state["detection_mode"])
    )
    st.session_state["detection_mode"] = detection_mode

    # 選択確定ボタン
    if st.button("選択確定"):
        if not st.session_state["selected_fids"]:
            st.warning("少なくとも1つのサンプルを選択してください。")
        else:
            # APIのベースURL
            base_url = "https://metabolites.in/foods/api/peaklist"

            fig = go.Figure()  # クロマトグラムの初期化
            pie_charts = []  # 円グラフのリスト

            # RT区間の凡例順序を固定
            bin_labels = ["0-20 min", "20-40 min", "40-60 min", "60-80 min", "80+ min"]

            for fid in st.session_state["selected_fids"]:
                sample_row = sample_list_df[sample_list_df['fid'] == fid]
                sample_name = sample_row['nameJa'].values[0] if not sample_row.empty else fid

                # APIリクエスト
                endpoint = f"{base_url}/{fid}/{detection_mode}"
                response = requests.get(endpoint)

                if response.status_code == 200:
                    # データを取得
                    peaklist = response.json()
                    data = pd.DataFrame(peaklist)

                    # --- クロマトグラムの処理 ---
                    # RT (Retention Time)とIntensityを取得
                    retention_time = data['rt']
                    intensity = data['intensity']

                    # RTを指定された幅で区切り、各区間の強度を合計
                    bin_edges = np.arange(retention_time.min(), retention_time.max() + rt_merge_width, rt_merge_width)
                    bin_indices = np.digitize(retention_time, bins=bin_edges)
                    binned_intensity = [intensity[bin_indices == i].sum() for i in range(1, len(bin_edges))]

                    # 組成割合（relative intensity）を計算
                    total_intensity = sum(binned_intensity)
                    relative_intensity = [val / total_intensity * 100 for val in binned_intensity]

                    # ビンの中心を計算
                    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

                    # グラフに追加
                    fig.add_trace(go.Scatter(
                        x=bin_centers,
                        y=relative_intensity,
                        mode='lines',
                        name=f'{sample_name} (ID: {fid})'
                    ))

                    # --- 円グラフの処理 ---
                    # 各RT区間の強度を合計
                    bins = [0, 20, 40, 60, 80, np.inf]
                    data['RT_range'] = pd.cut(retention_time, bins=bins, labels=bin_labels, right=False)

                    # 各区間の強度を合計
                    intensity_sum = data.groupby('RT_range')['intensity'].sum()
                    intensity_sum = intensity_sum.reindex(bin_labels, fill_value=0)  # ラベル順序を固定

                    # 円グラフデータを保存
                    pie_chart = go.Figure(data=[go.Pie(
                        labels=bin_labels,  # 固定ラベルを使用
                        values=intensity_sum.values,
                        hole=0.3,
                        sort=False,  # 並び替えを無効化
                        direction="clockwise"  # 時計回りに設定
                    )])
                    pie_chart.update_layout(
                        title=f'{sample_name} (ID: {fid})',
                        width=250,
                        height=250,
                        margin=dict(l=10, r=10, t=30, b=10)
                    )
                    pie_charts.append(pie_chart)

                else:
                    st.warning(f"サンプルID {fid} のデータ取得に失敗しました: {response.status_code}")

            # クロマトグラムを表示
            fig.update_layout(
                title='Chromatograms for Selected Samples (Relative Intensity)',
                xaxis_title='Retention Time (RT)',
                yaxis_title='Relative Intensity (%)',
                template='plotly_white',
                hovermode='x unified',
                width=1200,
                height=600,
                legend=dict(
                    x=0.02,
                    y=0.98,
                    bgcolor='rgba(255,255,255,0.5)',
                    bordercolor='black',
                    borderwidth=1
                )
            )
            st.plotly_chart(fig, use_container_width=True)

            # 円グラフを5個ずつ並べて表示
            cols = st.columns(5)
            for i, pie_chart in enumerate(pie_charts):
                with cols[i % 5]:
                    st.plotly_chart(pie_chart, use_container_width=True)

except FileNotFoundError:
    st.warning("サンプルリストのCSVファイルが見つかりません。ファイルパスを確認してください。")
