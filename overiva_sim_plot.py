# Copyright (c) 2019 Robin Scheibler
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""
This script takes the output from the simulation and produces a number of plots
used in the publication.
"""
import sys, argparse, os, json
import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("TkAgg")

import warnings
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

import pyroomacoustics as pra
from routines import grid_layout, semi_circle_layout, random_layout, gm_layout


def plot_room_setup(filename, n_mics, n_targets, parameters):
    """
    Plot the room scenario in 2D
    """

    n_interferers = parameters["n_interferers"]
    n_blinkies = parameters["n_blinkies"]
    ref_mic = parameters["ref_mic"]
    room_dim = np.array(parameters["room_dim"])

    # total number of sources
    n_sources = n_interferers + n_targets

    # Geometry of the room and location of sources and microphones
    interferer_locs = random_layout(
        [3.0, 5.5, 1.5], n_interferers, offset=[6.5, 1.0, 0.5], seed=1
    )

    target_locs = semi_circle_layout(
        [4.1, 3.755, 1.2],
        np.pi / 1.5,
        2.0,  # 120 degrees arc, 2 meters away
        n_targets,
        rot=0.743 * np.pi,
    )

    source_locs = np.concatenate((target_locs, interferer_locs), axis=1)

    if parameters["blinky_geometry"] == "gm":
        """ Normally distributed in the vicinity of each source """
        blinky_locs = gm_layout(
            n_blinkies,
            target_locs - np.c_[[0.0, 0.0, 0.5]],
            std=[0.4, 0.4, 0.05],
            seed=987,
        )

    elif parameters["blinky_geometry"] == "grid":
        """ Placed on a regular grid, with a little bit of noise added """
        blinky_locs = grid_layout(
            [3.0, 5.5], n_blinkies, offset=[1.0, 1.0, 0.7], seed=987
        )

    else:
        """ default is semi-circular """
        blinky_locs = semi_circle_layout(
            [4.1, 3.755, 1.1],
            np.pi,
            3.5,
            n_blinkies,
            rot=0.743 * np.pi - np.pi / 4,
            seed=987,
        )

    mic_locs = np.vstack(
        (
            pra.circular_2D_array([4.1, 3.76], n_mics, np.pi / 2, 0.02),
            1.2 * np.ones((1, n_mics)),
        )
    )
    all_locs = np.concatenate((mic_locs, blinky_locs), axis=1)

    # Create the room itself
    room = pra.ShoeBox(room_dim[:2])

    for loc in source_locs.T:
        room.add_source(loc[:2])

    # Place the microphone array
    room.add_microphone_array(pra.MicrophoneArray(all_locs[:2, :], fs=room.fs))

    room.plot(img_order=0)
    plt.xlim([-0.1, room_dim[0] + 0.1])
    plt.ylim([-0.1, room_dim[1] + 0.1])

    plt.savefig(filename)


if __name__ == "__main__":

    # parse arguments
    parser = argparse.ArgumentParser(
        description="Plot the data simulated by separake_near_wall"
    )
    parser.add_argument(
        "-p",
        "--pickle",
        action="store_true",
        help="Read the aggregated data table from a pickle cache",
    )
    parser.add_argument(
        "-s",
        "--show",
        action="store_true",
        help="Display the plots at the end of data analysis",
    )
    parser.add_argument(
        "dirs",
        type=str,
        nargs="+",
        metavar="DIR",
        help="The directory containing the simulation output files.",
    )

    cli_args = parser.parse_args()
    plot_flag = cli_args.show
    pickle_flag = cli_args.pickle

    parameters = dict()
    algorithms = dict()
    args = []
    df = None

    data_files = []

    for i, data_dir in enumerate(cli_args.dirs):

        print("Reading in", data_dir)

        # add the data file from this directory
        data_file = os.path.join(data_dir, "data.json")
        if os.path.exists(data_file):
            data_files.append(data_file)
        else:
            raise ValueError("File {} doesn" "t exist".format(data_file))

        # get the simulation config
        with open(os.path.join(data_dir, "parameters.json"), "r") as f:
            parameters = json.load(f)

    # algorithms to take in the plot
    algos = algorithms.keys()

    # check if a pickle file exists for these files
    pickle_file = ".mbss.pickle"

    if os.path.isfile(pickle_file) and pickle_flag:
        print("Reading existing pickle file...")
        # read the pickle file
        df = pd.read_pickle(pickle_file)

    else:

        # reading all data files in the directory
        records = []
        for file in data_files:
            with open(file, "r") as f:
                content = json.load(f)
                for seg in content:
                    records += seg

        # build the data table line by line
        print("Building table")
        columns = [
            "Algorithm",
            "Sources",
            "Mics",
            "RT60",
            "SINR",
            "seed",
            "Runtime [s]",
            "SDR [dB]",
            "SIR [dB]",
            "SDR Improvement [dB]",
            "SIR Improvement [dB]",
        ]
        table = []
        num_sources = set()

        copy_fields = ["algorithm", "n_targets", "n_mics", "rt60", "sinr", "seed"]

        for record in records:

            entry = [record[field] for field in copy_fields]

            # seconds processing / second of audio
            entry += [record["runtime"] / record["n_samples"] * parameters["fs"]]

            if np.isnan(record["runtime"]):
                warnings.warn("NaN runtime: {}".format(record["algorithm"]))

            if np.any(np.isnan(record["sdr"][-1])):
                warnings.warn("NaN SDR: {}".format(record["algorithm"]))

            if np.any(np.isnan(record["sir"][-1])):
                warnings.warn("NaN SIR: {}".format(record["algorithm"]))

            try:
                sdr_i = np.array(record["sdr"][0])  # Initial SDR
                sdr_f = np.array(record["sdr"][-1])  # Final SDR
                sir_i = np.array(record["sir"][0])  # Initial SDR
                sir_f = np.array(record["sir"][-1])  # Final SDR

                table.append(
                    entry
                    + [
                        np.mean(record["sdr"][-1]),
                        np.mean(record["sir"][-1]),
                        np.mean(sdr_f - sdr_i),
                        np.mean(sir_f - sir_i),
                    ]
                )
            except:
                continue

        # create a pandas frame
        print("Making PANDAS frame...")
        df = pd.DataFrame(table, columns=columns)
        df_melt = df.melt(id_vars=df.columns[: len(copy_fields)], var_name="metric")

        df.to_pickle(pickle_file)

    # Draw the figure
    print("Plotting...")

    # sns.set(style='whitegrid')
    # sns.plotting_context(context='poster', font_scale=2.)
    # pal = sns.cubehelix_palette(8, start=0.5, rot=-.75)

    substitutions = {
        "Algorithm": {
            "auxiva_laplace": "AuxIVA (Laplace)",
            "auxiva_gauss": "AuxIVA (Gauss)",
            "auxiva_pca_laplace": "PCA+AuxIVA (Laplace)",
            "auxiva_pca_gauss": "PCA+AuxIVA (Gauss)",
            "overiva_laplace": "OverIVA (Laplace)",
            "overiva_gauss": "OverIVA (Gauss)",
            "ogive_laplace": "OGIVEw (Laplace)",
            "ogive_gauss": "OGIVEw (Gauss)",
        }
    }

    df = df.replace(substitutions)
    df_melt = df_melt.replace(substitutions)

    all_algos = [
        "AuxIVA (Laplace)",
        "OverIVA (Laplace)",
        "PCA+AuxIVA (Laplace)",
        "OGIVEw (Laplace)",
        "AuxIVA (Gauss)",
        "OverIVA (Gauss)",
        "PCA+AuxIVA (Gauss)",
        "OGIVEw (Gauss)",
    ]

    sns.set(
        style="whitegrid",
        context="paper",
        font_scale=0.6,
        rc={
            #'figure.figsize': (3.39, 3.15),
            "lines.linewidth": 1.0,
            #'font.family': 'sans-serif',
            #'font.sans-serif': [u'Helvetica'],
            #'text.usetex': False,
        },
    )
    pal = sns.cubehelix_palette(
        4, start=0.5, rot=-0.5, dark=0.3, light=0.75, reverse=True, hue=1.0
    )
    sns.set_palette(pal)

    if not os.path.exists("figures"):
        os.mkdir("figures")

    fig_dir = "figures/{}_{}_{}".format(
        parameters["name"], parameters["_date"], parameters["_git_sha"]
    )

    if not os.path.exists(fig_dir):
        os.mkdir(fig_dir)

    fn_tmp = os.path.join(fig_dir, "RT60_{rt60}_SINR_{sinr}_{metric}.pdf")

    n_cols = len(np.unique(df["Sources"]))
    full_width = 6.93  # inches, == 17.6 cm, double column width
    aspect = 1.1  # width / height
    height = full_width / n_cols / aspect

    medians = {}
    the_metrics = {
        "improvements": ["SDR Improvement [dB]", "SIR Improvement [dB]"],
        "raw": ["SDR [dB]", "SIR [dB]"],
        "runtime": ["Runtime [s]"],
    }

    plt_kwargs = {
        # "improvements": {"ylim": [-5.5, 20.5], "yticks": [-5, 0, 5, 10, 15]},
        # "raw": {"ylim": [-5.5, 20.5], "yticks": [-5, 0, 5, 10, 15]},
        # "runtime": {"ylim": [-0.5, 40.5], "yticks": [0, 10, 20, 30]},
    }

    for rt60 in parameters["rt60_list"]:
        medians[rt60] = {}
        for sinr in parameters["sinr_list"]:
            medians[rt60][sinr] = {}

            select = np.logical_and(df_melt["RT60"] == rt60, df_melt["SINR"] == sinr)

            for m_name, metric in the_metrics.items():

                new_select = np.logical_and(select, df_melt.metric.isin(metric))

                g = sns.catplot(
                    data=df_melt[select],
                    x="Mics",
                    y="value",
                    hue="Algorithm",
                    col="Sources",
                    row="metric",
                    row_order=metric,
                    hue_order=all_algos,
                    kind="box",
                    legend=False,
                    aspect=aspect,
                    height=height,
                    linewidth=0.5,
                    fliersize=0.3,
                    sharey="row",
                    # size=3, aspect=0.65,
                    margin_titles=True,
                )

                if m_name in plt_kwargs:
                    g.set(**plt_kwargs[metric])
                # remove original titles before adding custom ones
                [plt.setp(ax.texts, text="") for ax in g.axes.flat]
                g.set_titles(col_template="Sources={col_name}", row_template="")

                all_artists = []

                # left_ax = g.facet_axis(2, 0)
                left_ax = g.facet_axis(len(metric) - 1, n_cols - 1)
                leg = left_ax.legend(
                    title="Algorithms",
                    frameon=True,
                    framealpha=0.85,
                    fontsize="x-small",
                    loc="upper left",
                    bbox_to_anchor=[-0.05, 1.35],
                )
                leg.get_frame().set_linewidth(0.2)
                all_artists.append(leg)

                sns.despine(offset=10, trim=False, left=True, bottom=True)

                plt.tight_layout(pad=0.01)

                for c, lbl in enumerate(metric):
                    g_ax = g.facet_axis(c, 0)
                    g_ax.set_ylabel(lbl)

                rt60_name = str(int(float(rt60) * 1000)) + "ms"
                fig_fn = fn_tmp.format(rt60=rt60_name, sinr=sinr, metric=m_name)
                plt.savefig(fig_fn, bbox_extra_artists=all_artists, bbox_inches="tight")
                plt.close()

                # also get only the median information out
                medians[rt60][sinr][m_name] = []
                for sub_df in g.facet_data():
                    medians[rt60][sinr][m_name].append(
                        sub_df[1].pivot_table(
                            values="value",
                            columns="Mics",
                            index=["Algorithm", "Sources", "RT60", "SINR", "metric"],
                            aggfunc="median",
                        )
                    )

            # Now we want to analyze the median in a meaningful way
            algo_merge = {
                "AuxIVA (Laplace)": "AuxIVA",
                "OverIVA (Laplace)": "OverIVA",
                "PCA+AuxIVA (Laplace)": "PCA+AuxIVA",
                "OGIVEw (Laplace)": "OGIVEw",
                "AuxIVA (Gauss)": "AuxIVA",
                "OverIVA (Gauss)": "OverIVA",
                "PCA+AuxIVA (Gauss)": "PCA+AuxIVA",
                "OGIVEw (Gauss)": "OGIVEw",
            }
            # First plot for 1 source only
            new_select = np.logical_and(select, df_melt["Sources"] == 1)
            new_select = np.logical_and(new_select, df_melt["metric"] == "Runtime [s]")
            g = sns.catplot(
                data=df_melt[new_select].replace(algo_merge),
                x="Mics",
                y="value",
                hue="Algorithm",
                col="Sources",
                row="metric",
                row_order=["Runtime [s]"],
                # col_order=[1],
                hue_order=["OGIVEw", "AuxIVA", "OverIVA"],
                kind="point",
                legend=False,
                aspect=aspect,
                height=height,
                # linewidth=0.5,
                estimator=np.median,
                ci=None,
                scale=0.75,
                # fliersize=0.3,
                sharey="row",
                # size=3, aspect=0.65,
                # margin_titles=True,
            )
            sns.despine(offset=10, trim=False, left=True, bottom=True)
            left_ax = g.facet_axis(0, 0)
            leg = left_ax.legend(
                title="Algorithms",
                frameon=True,
                framealpha=0.85,
                fontsize="x-small",
                # loc="center left",
                bbox_to_anchor=[0.4, 0.65],
            )
            leg.get_frame().set_linewidth(0.2)
            g.set_titles("Single source")
            g_ax = g.facet_axis(0, 0)
            g_ax.set_ylabel("Real-time factor [s]")
            fig_fn = fn_tmp.format(rt60=rt60_name, sinr=sinr, metric="runtime_agg")
            plt.yticks([0.0, 1.0, 5.0, 10])
            plt.savefig(fig_fn, bbox_inches="tight")

            df_med = df.loc[select].replace(algo_merge)
            pvtb = df_med.pivot_table(
                columns=["Algorithm", "Sources"],
                index="Mics",
                values="Runtime [s]",
                aggfunc="median",
            )

            def proc_ratio(r):
                pts = []
                for src in np.unique(r.columns.get_level_values("Sources")):
                    for mic in r.index:
                        if not np.isnan(r[src][mic]):
                            pts.append([src / mic, r[src][mic]])
                arr = np.array(pts)
                o = np.argsort(arr[:, 0])
                return arr[o, :]

            ratio_overiva = proc_ratio(pvtb["OverIVA"] / pvtb["AuxIVA"])
            ratio_pca = proc_ratio(pvtb["PCA+AuxIVA"] / pvtb["AuxIVA"])
            ratio_ogive = proc_ratio(pvtb["OGIVEw"] / pvtb["AuxIVA"])

            mrksz = 4
            lw = 1.5

            plt.figure(figsize=(height, height))
            plt.plot([0, 1], [0, 1], "--", label="$x=y$", linewidth=lw)
            plt.plot(
                ratio_overiva[:, 0],
                ratio_overiva[:, 1],
                "o",
                label="OverIVA",
                clip_on=False,
                markersize=mrksz,
                linewidth=lw,
            )
            plt.plot(
                ratio_pca[:, 0],
                ratio_pca[:, 1],
                "x",
                label="PCA+AuxIVA",
                clip_on=False,
                markersize=mrksz,
                linewidth=lw,
            )
            plt.xlim([0.0, 1.0])
            plt.ylim([-0.05, 1.1])
            plt.xlabel("Ratio of sources to microphones ($K/M$)")
            plt.ylabel("Median runtime ratio to AuxIVA")
            plt.axis("equal")
            plt.grid(False, axis="x")
            sns.despine(offset=10, trim=False, left=True, bottom=True)
            leg = plt.legend(loc="upper left", bbox_to_anchor=[-0.05, 1])
            leg.get_frame().set_linewidth(0.2)

            rt60_name = str(int(float(rt60) * 1000)) + "ms"
            fig_fn = fn_tmp.format(rt60=rt60_name, sinr=sinr, metric="runtime_ratio")
            plt.savefig(fig_fn, bbox_inches="tight")
            plt.close()

    if plot_flag:
        plt.show()
