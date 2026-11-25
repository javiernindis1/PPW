
import json
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import networkx as nx

from pyvis.network import Network

from crawler_logic import crawl_and_analyze


# ==========================================
# KONFIGURASI STREAMLIT
# ==========================================

st.set_page_config(
    page_title="Web Crawler & PageRank",
    page_icon="🌐",
    layout="wide"
)

st.title("🌐 Web Crawler & PageRank")

st.write(
    "Crawling website multi-domain, "
    "visualisasi directed graph, dan "
    "perhitungan PageRank."
)


# ==========================================
# SESSION STATE
# ==========================================

if "result" not in st.session_state:
    st.session_state.result = None

if "selected_node" not in st.session_state:
    st.session_state.selected_node = None


# ==========================================
# FUNGSI VISUALISASI GRAPH
# ==========================================

def visualize_graph(
    graph,
    pagerank,
    focus_node=None,
    figsize=None
):

    net = Network(
        height="650px",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#222222",
        cdn_resources="in_line"
    )

    max_pr = max(
        pagerank.values()
    ) if pagerank else 0

    # Menambahkan node.
    for node in graph.nodes():

        score = pagerank.get(node, 0)

        if max_pr > 0:
            size = 15 + (score / max_pr * 35)
        else:
            size = 15

        parsed = urlparse(node)

        label = parsed.netloc

        net.add_node(
            node,
            label=label,
            title=(
                f"URL: {node}<br>"
                f"PageRank: {score:.8f}<br>"
                f"In-Degree: {graph.in_degree(node)}<br>"
                f"Out-Degree: {graph.out_degree(node)}"
            ),
            size=size
        )

    # Menambahkan edge.
    for source, target in graph.edges():

        net.add_edge(
            source,
            target,
            arrows="to"
        )

    net.set_options("""
    {
        "physics": {
            "enabled": true,
            "solver": "barnesHut",
            "barnesHut": {
                "gravitationalConstant": -3000,
                "centralGravity": 0.3,
                "springLength": 150,
                "springConstant": 0.04,
                "damping": 0.12
            },
            "stabilization": {
                "enabled": true,
                "iterations": 500
            }
        },
        "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true,
            "zoomView": true
        },
        "edges": {
            "smooth": {
                "enabled": true,
                "type": "dynamic"
            }
        }
    }
    """)

    html = net.generate_html()

    # Tambahkan interaksi klik node.
    marker = "network = new vis.Network(container, data, options);"

    focus_json = json.dumps(focus_node)

    custom_js = f"""
    const allNodeIds = network.body.data.nodes.getIds();
    const allEdgeIds = network.body.data.edges.getIds();

    const resetButton = document.createElement("button");

    resetButton.innerText = "Tampilkan Semua Node";

    resetButton.style.cssText = `
        position:absolute;
        top:10px;
        left:10px;
        z-index:1000;
        padding:10px 15px;
        background:white;
        border:1px solid #aaa;
        border-radius:6px;
        cursor:pointer;
        display:none;
    `;

    document.body.appendChild(resetButton);

    function showAll() {{

        network.body.data.nodes.update(
            allNodeIds.map(id => ({{id:id, hidden:false}}))
        );

        network.body.data.edges.update(
            allEdgeIds.map(id => ({{id:id, hidden:false}}))
        );

        resetButton.style.display = "none";

        network.fit();
    }}

    function showNeighbors(nodeId) {{

        const neighbors = network.getConnectedNodes(nodeId);

        const visible = new Set([
            nodeId,
            ...neighbors
        ]);

        network.body.data.nodes.update(
            allNodeIds.map(id => ({{
                id:id,
                hidden:!visible.has(id)
            }}))
        );

        const edges = network.body.data.edges.get();

        network.body.data.edges.update(
            edges.map(edge => ({{
                id:edge.id,
                hidden:!(
                    visible.has(edge.from) &&
                    visible.has(edge.to)
                )
            }}))
        );

        resetButton.style.display = "block";

        network.fit({{
            nodes:Array.from(visible),
            animation:true
        }});

        network.selectNodes([nodeId]);
    }}

    resetButton.addEventListener("click", showAll);

    network.on("click", function(params) {{

        if (params.nodes.length > 0) {{

            showNeighbors(params.nodes[0]);

        }}

    }});

    const requestedFocus = {focus_json};

    if (
        requestedFocus &&
        network.body.data.nodes.get(requestedFocus)
    ) {{

        showNeighbors(requestedFocus);

        network.focus(requestedFocus, {{
            scale:1.2,
            animation:true
        }});

    }}

    network.on("stabilizationIterationsDone", function() {{

        network.setOptions({{
            physics: {{
                enabled:false
            }}
        }});

    }});
    """

    if marker in html:
        html = html.replace(
            marker,
            marker + custom_js,
            1
        )

    return html


# ==========================================
# SIDEBAR
# ==========================================

with st.sidebar:

    st.header("⚙️ Pengaturan Crawling")

    with st.form("crawler_form"):

        start_url = st.text_input(
            "URL Awal",
            placeholder="https://example.com"
        )

        max_pages = st.number_input(
            "Maksimal Domain",
            min_value=1,
            max_value=500,
            value=50
        )

        max_depth = st.number_input(
            "Depth Crawling",
            min_value=0,
            max_value=10,
            value=2
        )

        delay = st.slider(
            "Delay Request (detik)",
            min_value=0.0,
            max_value=2.0,
            value=0.3,
            step=0.1
        )

        submit = st.form_submit_button(
            "🚀 Mulai Crawling",
            use_container_width=True
        )

    st.divider()

    st.caption(
        "Setiap hostname hanya dicrawl satu kali. "
        "Path seperti /image, /info, dan /about "
        "akan dinormalisasi menjadi root domain."
    )


# ==========================================
# PROSES CRAWLING
# ==========================================

if submit:

    if not start_url.strip():

        st.error("Masukkan URL terlebih dahulu.")

    else:

        progress = st.progress(0)

        status = st.empty()

        def update_progress(
            current,
            maximum,
            current_url
        ):

            percent = int(
                current / maximum * 100
            )

            progress.progress(
                min(percent, 100)
            )

            status.info(
                f"Crawling: {current}/{maximum}\n\n"
                f"URL: {current_url}"
            )

        try:

            with st.spinner("Sedang melakukan crawling..."):

                result = crawl_and_analyze(
                    start_url=start_url,
                    max_depth=int(max_depth),
                    max_pages=int(max_pages),
                    delay=float(delay),
                    progress_callback=update_progress
                )

            st.session_state.result = result

            st.session_state.selected_node = None

            progress.progress(100)

            status.success("Crawling selesai!")

        except Exception as e:

            st.error(
                f"Terjadi kesalahan: {str(e)}"
            )


# ==========================================
# HASIL CRAWLING
# ==========================================

result = st.session_state.result

if result:

    graph = result["graph"]

    pagerank = result["pagerank"]

    rankings = result["rankings"]

    stats = result["stats"]

    st.divider()

    st.header("📊 Statistik Crawling")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Domain Dicrawl",
        stats["visited"]
    )

    col2.metric(
        "Total Node",
        stats["nodes"]
    )

    col3.metric(
        "Total Edge",
        stats["edges"]
    )

    col4.metric(
        "Graph Density",
        f"{stats['density']:.4f}"
    )

    st.caption(
        f"URL awal: {result['start_url']}"
    )

    st.divider()

    # ======================================
    # TABS
    # ======================================

    tab_graph, tab_rank, tab_urls, tab_error = st.tabs([
        "🕸️ Graph",
        "🏆 PageRank",
        "🔗 URL Dicrawl",
        "⚠️ Error"
    ])

    # ======================================
    # GRAPH
    # ======================================

    with tab_graph:

        st.subheader("Visualisasi Directed Graph")

        node_options = [
            "Semua Node"
        ] + list(graph.nodes())

        selected = st.selectbox(
            "Pilih node untuk difokuskan",
            node_options,
            format_func=lambda x: (
                x if x == "Semua Node"
                else urlparse(x).netloc
            )
        )

        focus_node = (
            None if selected == "Semua Node"
            else selected
        )

        graph_html = visualize_graph(
            graph,
            pagerank,
            focus_node=focus_node
        )

        components.html(
            graph_html,
            height=680,
            scrolling=False
        )

        st.caption(
            "Klik node untuk menampilkan node tersebut "
            "beserta node yang terhubung langsung dengannya. "
            "Klik tombol Tampilkan Semua Node untuk kembali."
        )

        st.info(
            "Ukuran node menunjukkan nilai PageRank. "
            "Arah panah menunjukkan hubungan link antar-domain."
        )

    # ======================================
    # RANKING
    # ======================================

    with tab_rank:

        st.subheader("🏆 Ranking Website")

        st.write(
            "Ranking ditentukan berdasarkan jumlah "
            "In-Degree tertinggi. Jika nilainya sama, "
            "digunakan PageRank sebagai urutan berikutnya."
        )

        ranking_df = pd.DataFrame(rankings)

        ranking_display = ranking_df[
            [
                "rank",
                "url",
                "inlinks",
                "outlinks",
                "pagerank"
            ]
        ].copy()

        ranking_display.columns = [
            "Rank",
            "URL",
            "In-Degree",
            "Out-Degree",
            "PageRank"
        ]

        st.dataframe(
            ranking_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "URL": st.column_config.LinkColumn(
                    "URL",
                    display_text="Buka URL"
                ),
                "PageRank": st.column_config.NumberColumn(
                    "PageRank",
                    format="%.8f"
                )
            }
        )

        st.divider()

        st.subheader("Fokuskan Website pada Graph")

        selected_rank_url = st.selectbox(
            "Pilih website dari ranking",
            [item["url"] for item in rankings],
            format_func=lambda x: urlparse(x).netloc,
            key="ranking_selected_url"
        )

        if st.button("Tampilkan pada Graph"):

            st.session_state.selected_node = selected_rank_url

            st.session_state.graph_focus = selected_rank_url

            st.success(
                "Website dipilih. Buka tab Graph dan pilih domain tersebut."
            )

    # ======================================
    # URL DICRAWL
    # ======================================

    with tab_urls:

        st.subheader("Daftar Domain yang Berhasil Dicrawl")

        urls_df = pd.DataFrame({
            "No": range(
                1,
                len(result["crawled_urls"]) + 1
            ),
            "URL": result["crawled_urls"]
        })

        st.dataframe(
            urls_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "URL": st.column_config.LinkColumn(
                    "URL"
                )
            }
        )

    # ======================================
    # ERROR
    # ======================================

    with tab_error:

        st.subheader("Catatan Error")

        if result["errors"]:

            st.dataframe(
                pd.DataFrame(result["errors"]),
                use_container_width=True,
                hide_index=True
            )

        else:

            st.success(
                "Tidak ditemukan error."
            )

    # ======================================
    # DOWNLOAD
    # ======================================

    st.divider()

    st.header("📥 Download Hasil")

    export_json = {
        "start_url": result["start_url"],
        "stats": stats,
        "pagerank": pagerank,
        "rankings": rankings,
        "crawled_urls": result["crawled_urls"],
        "graph": nx.node_link_data(
            graph,
            edges="edges"
        ),
        "errors": result["errors"]
    }

    col1, col2 = st.columns(2)

    with col1:

        st.download_button(
            "⬇️ Download JSON",
            data=json.dumps(
                export_json,
                indent=4,
                ensure_ascii=False
            ),
            file_name="crawl_results.json",
            mime="application/json",
            use_container_width=True
        )

    with col2:

        st.download_button(
            "⬇️ Download CSV Ranking",
            data=pd.DataFrame(
                rankings
            ).to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="pagerank_ranking.csv",
            mime="text/csv",
            use_container_width=True
        )

else:

    st.info(
        "Belum ada hasil crawling. "
        "Masukkan URL awal pada sidebar untuk memulai."
    )
