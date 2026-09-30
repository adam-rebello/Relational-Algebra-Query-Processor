import matplotlib.pyplot as plt


join_sizes = [
    1000,
    2000,
    4000,
    8000,
    16000,
    32000,
    64000
]

join_times = [
    1.746642,
    6.902448,
    35.038906,
    112.305770,
    439.774611,
    2171.982749,
    8712.435958
]

select_times = [
    0.000901,
    0.001772,
    0.003499,
    0.006953,
    0.013635,
    0.027283,
    0.060652
]

project_times = [
    0.001904,
    0.004230,
    0.007652,
    0.015640,
    0.030696,
    0.061421,
    0.125770
]


plt.figure()

plt.loglog(
    join_sizes,
    join_times,
    marker="o",
    label="Join"
)

plt.loglog(
    join_sizes,
    select_times,
    marker="o",
    label="Select"
)

plt.loglog(
    join_sizes,
    project_times,
    marker="o",
    label="Project"
)

plt.xlabel("Number of tuples")
plt.ylabel("Wall time (seconds)")
plt.title("Relational Operator Performance")

plt.legend()
plt.grid(True)

plt.tight_layout()

plt.savefig(
    "performance_loglog.png",
    dpi=300
)

print(
    "Saved graph to performance_loglog.png"
)