"""
plots.py — visualizations for the eval notebooks. Seaborn on top of matplotlib.

Every function takes the raw long-format DataFrames (as written by process_csv /
the staircase runner) or the `cells_of()` output from analysis.py — never a
pre-aggregated single number — so the plot always shows the underlying spread,
not just a mean that can hide a bimodal distribution the way exp 4's did.
Seaborn does the aggregation itself and draws a 95% CI by default, so the spread
is visible without hand-rolling it.

RUBRIC_EDGES matches the confidence rubric in the system prompt (prompt_builder.py)
exactly: [0.00, 0.01-0.09, 0.10-0.39, 0.40-0.69, 0.70-0.89, 0.90-1.00]. Confidence
is quantized to these bands in practice (the model clusters at values like 0.28,
0.78, 0.96 rather than spreading continuously) — plotting against the model's
actual bands, not arbitrary quartile cuts, is what makes the shape legible.
"""

from __future__ import annotations
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

sns.set_theme(style='whitegrid', context='notebook')

RUBRIC_EDGES = [0.0, 0.01, 0.10, 0.40, 0.70, 0.90, 1.001]
RUBRIC_LABELS = ['none\n(0.00)', 'forced\nguess', 'vague\nguess', 'partial/\nindirect',
                 'strong\ninference', 'explicit\nmatch']
DIFFICULTY_ORDER = ['unambiguous_candidate', 'boundary_candidate', 'thin',
                    'edge_no_signal', 'edge_cultivated']

# Not hand-picked hexes, but still a fixed dict rather than letting seaborn assign
# per-plot: colors must mean the same thing across plots even when a given frame
# only contains a subset of the difficulty tags.
DIFFICULTY_PALETTE = dict(zip(DIFFICULTY_ORDER, sns.color_palette('deep', len(DIFFICULTY_ORDER))))


def _difficulty_order(present) -> list[str]:
    return [d for d in DIFFICULTY_ORDER if d in set(present)]


def _short(d: str) -> str:
    return d.replace('_candidate', '')


def _rubric_lines(ax, axis: str = 'x'):
    """Draws the rubric's actual band boundaries (0.09/0.39/0.69/0.89), not
    arbitrary quartile cuts. Every confidence-adjacent plot needs this line —
    factored out so there's one place that knows where the bands actually are."""
    line_fn = ax.axvline if axis == 'x' else ax.axhline
    for edge in RUBRIC_EDGES[1:-1]:
        line_fn(edge, color='grey', linestyle=':', linewidth=0.7, alpha=0.5)


def _label_counts(ax, counts, container=0):
    """Annotate a bar container with n= per bar. Kept (and kept mandatory) because
    omitting the count is exactly what made exp 4's calibration bars readable as a
    finding when the real n was 7."""
    ax.bar_label(ax.containers[container], labels=[f'n={int(n)}' for n in counts],
                 padding=3, fontsize=8, color='#333')


# --- 1. confidence distribution -----------------------------------------------

def plot_confidence_hist(df: pd.DataFrame, title: str = 'Confidence distribution',
                         ax=None):
    """Histogram against the RUBRIC's actual bands, not arbitrary quartile cuts.
    Confidence is quantized (the model lands on discrete values within each rubric
    band), so a plain equal-width histogram or a naive [0,.4,.7,1] cut can make an
    evenly-behaved distribution look noisy purely from where the bin edges fall.
    No KDE here — smoothing quantized values invents a shape that isn't there."""
    fig, ax = (None, ax) if ax is not None else plt.subplots(figsize=(8, 4))
    sns.histplot(df, x='clc_confidence', bins=np.linspace(0, 1, 41), ax=ax)
    _rubric_lines(ax, axis='x')
    ax.set(xlabel='confidence', ylabel='count', title=title, xlim=(0, 1))
    return fig


def plot_working_vs_heldout_confidence(working: pd.DataFrame, heldout: pd.DataFrame,
                                       labels=('working', 'heldout')):
    """Density-normalized histograms, one hue per set — the shape comparison a mean
    can hide (this is what exposed the working/held-out confidence gap as
    difficulty-mix, not drift: the two distributions have the same teeth, different
    heights). `common_norm=False` is the whole point: normalize each set to itself,
    otherwise the bigger set just looks taller."""
    both = pd.concat([working.assign(set=labels[0]), heldout.assign(set=labels[1])])

    fig, ax = plt.subplots(figsize=(8, 4))
    sns.histplot(both, x='clc_confidence', hue='set', stat='density',
                 common_norm=False, bins=np.linspace(0, 1, 41),
                 element='step', alpha=0.4, ax=ax)
    _rubric_lines(ax, axis='x')
    ax.set(xlabel='confidence', ylabel='density', xlim=(0, 1),
           title='Confidence distribution: working vs heldout')
    return fig


def plot_confidence_by_difficulty(df: pd.DataFrame, title='Confidence by difficulty'):
    """Boxplot per difficulty tag — this is usually where a flat mean_conf hides
    the real story (e.g. thin rows sitting at ~0.3-0.5 while boundary rows sit
    at ~0.8-0.9, averaging out to something in between that describes neither).
    Strip overlay because the values are quantized: the box says where the mass is,
    the dots say it's sitting on three discrete values, which a box alone implies
    is a continuum. Deliberately not a violin — the KDE would smooth that away."""
    order = _difficulty_order(df['difficulty'].unique())

    fig, ax = plt.subplots(figsize=(8, 4.5))
    sns.violinplot(df, x='difficulty', y='clc_confidence', order=order, hue='difficulty',
                palette=DIFFICULTY_PALETTE, legend=False, 
                width=0.6, ax=ax)

    _rubric_lines(ax, axis='y')
    ax.set_xticklabels([_short(d) for d in order])
    ax.set(xlabel='', ylabel='confidence', ylim=(0, 1), title=title)
    return fig


# --- 2. exp 2: the staircase --------------------------------------------------

def plot_staircase(cells: pd.DataFrame, metrics=('mean_conf', 'consistency', 'agree_L1'),
                   version_col='version', title='Staircase: metric by version'):
    """One line per metric across v0..v5. Put mean_conf and agree_L1 on the same
    axes deliberately — this is the plot that shows DECALIBRATION at a glance:
    confidence climbing while agreement stays flat, which the numbers-only table
    makes you compute by hand. Passing the cells (not the means) lets seaborn draw
    the CI band, so a 'rise' that's inside the noise looks like one."""
    long = cells.melt(id_vars=version_col, value_vars=list(metrics),
                      var_name='metric', value_name='score')

    fig, ax = plt.subplots(figsize=(8, 4.5))
    sns.lineplot(long, x=version_col, y='score', hue='metric', style='metric',
                 markers=True, dashes=False, linewidth=2, ax=ax)
    ax.set(xlabel='version', ylabel='score', ylim=(0, 1), title=title)
    ax.set_xticks(sorted(cells[version_col].unique()))
    return fig


def plot_agreement_by_difficulty_and_version(cells: pd.DataFrame, level='agree_L1',
                                             title=None):
    """The sub-MMU inversion, visually: grouped bars per version, one group per
    difficulty. If `unambiguous` bars sit BELOW `thin` bars, that's the reference
    rewarding the model for ignoring the habitat text — the thing a single
    'agree_L1 = 0.33' number cannot show. Error bars come free from the cells."""
    order = _difficulty_order(cells['difficulty'].unique())

    fig, ax = plt.subplots(figsize=(9, 4.5))
    sns.barplot(cells, x='version', y=level, hue='difficulty', hue_order=order,
                palette=DIFFICULTY_PALETTE, ax=ax)
    ax.set(ylabel=level, ylim=(0, 1),
           title=title or f'{level} by difficulty and version')
    ax.set_xticklabels([f'v{v}' for v in sorted(cells['version'].unique())])
    handles, lbls = ax.get_legend_handles_labels()
    ax.legend(handles, [_short(d) for d in lbls], fontsize=8, title=None)
    return fig


# --- 3. exp 3: model comparison ------------------------------------------------

def plot_model_comparison(comp: pd.DataFrame, metrics=('consistency', 'agree_L1', 'mean_conf'),
                          model_col='model'):
    """Grouped bars, one group per model. `comp` = the summary table already built
    in the exp-3 notebook (one row per model)."""
    long = comp.melt(id_vars=model_col, value_vars=list(metrics),
                     var_name='metric', value_name='score')

    fig, ax = plt.subplots(figsize=(9, 4.5))
    sns.barplot(long, x=model_col, y='score', hue='metric', ax=ax)
    ax.set(xlabel='', ylim=(0, 1), title='Model comparison')
    ax.tick_params(axis='x', rotation=20)
    return fig


def plot_cost_vs_quality(comp: pd.DataFrame, quality_col='consistency',
                         cost_col='cost_per_100k', model_col='model'):
    """Scatter: cost on log-x, quality on y. Makes the cheap-good-enough question
    visual — a model in the upper-left dominates everything to its lower-right."""
    fig, ax = plt.subplots(figsize=(7, 5))
    sns.scatterplot(comp, x=cost_col, y=quality_col, hue=model_col, s=90,
                    legend=False, ax=ax)
    for _, r in comp.iterrows():
        ax.annotate(r[model_col], (r[cost_col], r[quality_col]),
                    textcoords='offset points', xytext=(6, 6), fontsize=9)
    ax.set_xscale('log')
    ax.set(xlabel=f'{cost_col} (log scale)', ylabel=quality_col,
           title='Cost vs quality (upper-left is ideal)')
    return fig


def plot_flip_rate(stability: pd.DataFrame, model_col='model', rate_col='flip_rate'):
    """Bar chart of prompt-instability. The finding that EVERY model flips 48-75%
    of codes on a trivial prompt reorder is easy to miss in a table; a bar chart
    with all of them clustered high makes it unmissable that this is universal,
    not a single-model weakness."""
    order = stability.sort_values(rate_col)

    fig, ax = plt.subplots(figsize=(7, 4))
    sns.barplot(order, x=rate_col, y=model_col, orient='h', ax=ax)
    ax.bar_label(ax.containers[0], fmt='%.2f', padding=3, fontsize=8)
    ax.set(xlim=(0, 1), xlabel='code flip rate (v0 -> v4)', ylabel='',
           title='Prompt-stability (lower = more robust)')
    return fig


# --- 4. calibration -------------------------------------------------------------

def plot_calibration(cal: pd.DataFrame, title='Calibration: does confidence track agreement?'):
    """cal = the output of analysis.calibration() (mean/count per rubric band).
    Bar height = agreement, annotation = sample size, since a small band (exp 4's
    held-out `low` band was n=7) can swing wildly and that MUST be visible, not
    hidden behind a single number."""
    d = cal.rename_axis('band').reset_index()

    fig, ax = plt.subplots(figsize=(6, 4))
    sns.barplot(d, x='band', y='mean', ax=ax)
    _label_counts(ax, d['count'])
    ax.axhline(d['mean'].mean(), color='grey', linestyle=':', linewidth=0.8)
    ax.set(xlabel='', ylim=(0, 1), ylabel='agreement with CLC', title=title)
    return fig


def plot_calibration_comparison(cal_a: pd.DataFrame, cal_b: pd.DataFrame,
                                labels=('working', 'heldout')):
    """Calibration for two sets/models on shared axes — the working-vs-held-out or
    model-vs-model check. One panel with hue rather than two side-by-side panels:
    the comparison is per-band, and dodged bars put the two versions of a band
    adjacent instead of a screen apart. Sample sizes annotated so a thin band
    doesn't get read as a solid finding."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, cal, lbl in zip(axes, [cal_a, cal_b], labels):
        d = cal.rename_axis('band').reset_index()
        sns.barplot(d, x='band', y='mean', ax=ax)
        _label_counts(ax, d['count'])
        ax.set(xlabel='', ylim=(0, 1), title=lbl)
    axes[0].set_ylabel('agreement with CLC')
    fig.suptitle('Calibration comparison')
    fig.tight_layout()
    return fig


# --- 5. top-3 / v5 ---------------------------------------------------------------

def plot_topn_signals(v5: pd.DataFrame):
    """v5 = the output of analysis.topn_signals(). Two panels: confidence gap by
    difficulty (shows the INVERTED relationship — small gap = thin text, not
    ambiguity) and L1-spread by difficulty (the metric that actually flags
    genuine boundary cases)."""
    order = _difficulty_order(v5['difficulty'].unique())
    panels = [
        ('conf_gap', 'Confidence gap (small = NO SIGNAL, not ambiguity)',
         'match[0] - match[1] confidence', (0, None)),
        ('l1_spread', 'L1-spread across top-3 (2-3 = genuine ambiguity flag)',
         'distinct L1 families in top-3', (1, 3)),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, (col, title, ylabel, ylim) in zip(axes, panels):
        sns.barplot(v5, x='difficulty', y=col, order=order, hue='difficulty',
                    palette=DIFFICULTY_PALETTE, legend=False, ax=ax)
        ax.set_xticklabels([_short(d) for d in order], rotation=20, ha='right')
        ax.set(xlabel='', ylabel=ylabel, title=title, ylim=ylim)
    fig.tight_layout()
    return fig


# --- 6. cost -------------------------------------------------------------------

def plot_cost_by_version(cost: pd.Series, title='Cost by version'):
    fig, ax = plt.subplots(figsize=(7, 4))
    sns.barplot(x=[f'v{i}' for i in cost.index], y=cost.values, ax=ax)
    ax.bar_label(ax.containers[0], fmt='$%.4f', padding=3, fontsize=8)
    ax.set(ylabel='USD', title=title)
    return fig