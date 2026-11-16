"""Plots for the measurement report; reads recorded CSV, no invented values."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]/'measurements_m2'
with (ROOT/'join_cost.csv').open(newline='') as f:rows=list(csv.DictReader(f))
labels={'nested_loop_join':'Block nested loop','sort_merge_join':'Sort merge','hash_join':'Grace hash'}
fig,ax=plt.subplots(figsize=(7,4))
for op,label in labels.items():
    data=sorted((int(r['frames']),int(r['measured_reads'])+int(r['measured_writes'])) for r in rows if r['join']==op and r['rows_each']=='600')
    ax.plot([x for x,y in data],[y for x,y in data],marker='o',label=label)
ax.set(xlabel='Buffer frames (B)',ylabel='Page I/O (reads + writes)',title='Join I/O by memory budget — 600 rows per input')
ax.set_xscale('log',base=2);ax.legend();fig.tight_layout()
fig.savefig(ROOT/'join_io_by_frames.png',dpi=150);plt.close(fig)
fig,ax=plt.subplots(figsize=(7,4))
for op,label in labels.items():
    data=sorted((int(r['rows_each']),int(r['measured_reads'])+int(r['measured_writes'])) for r in rows if r['join']==op and r['frames']=='4')
    ax.plot([x for x,y in data],[y for x,y in data],marker='o',label=label)
ax.set(xlabel='Rows per input (B = 4)',ylabel='Page I/O (reads + writes)',title='Join I/O by input size')
ax.legend();fig.tight_layout()
fig.savefig(ROOT/'join_io_by_size.png',dpi=150);plt.close(fig)
