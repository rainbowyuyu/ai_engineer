import matplotlib.pyplot as plt
import numpy as np

# ----------------- 全局字体与图形规范设置 (Nature 风格) -----------------
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['axes.linewidth'] = 1.2
plt.rcParams['mathtext.default'] = 'regular'

color_ai = '#089981'
color_tq = '#DF4D3B'

# 统一的基础图像宽度，确保所有主图（b, c, d, e）宽度完全一致
FIG_WIDTH = 15
FIG_HEIGHT = 5.0

def plot_nature_bar(ax, title, data_dict, ylabel='', limit=None, limit_label=''):
    """通用 Nature 风格柱状图绘制函数，带限值与差异百分比标注"""
    ai_val = data_dict['AI']
    tq_val = data_dict['Tuqiang']
    
    bars = ax.bar(['AI', 'Tuqiang'], [ai_val, tq_val], color=[color_ai, color_tq], width=0.55)
    
    for bar in bars:
        yval = bar.get_height()
        label = f"{yval:,.0f}" if yval >= 1000 else f"{yval:.2f}"
        ax.text(bar.get_x() + bar.get_width()/2, yval + (max(ai_val, tq_val)*0.03), 
                label, ha='center', va='bottom', fontsize=14, fontweight='bold')
    
    max_y = max(ai_val, tq_val)
    
    # 添加限值虚线与标签（仅当 limit 不为 None 时）
    if limit is not None:
        ax.axhline(y=limit, color='#7f8c8d', linestyle='--', linewidth=1.5, zorder=0)
        ax.text(0.5, limit + max_y*0.05, f"Limit: {limit_label}", color='#7f8c8d', va='center', ha='center', fontsize=11, fontweight='bold')
        max_y = max(max_y, limit)
        
    # 添加差异百分比标签
    pct_diff = (ai_val - tq_val) / tq_val * 100
    box_color = color_ai if pct_diff < 0 else color_tq
    sign = "+" if pct_diff > 0 else ""
    bbox_props = dict(boxstyle="round,pad=0.3", fc="white", ec=box_color, lw=1.2)
    ax.text(0.5, max_y * 1.25, f"{sign}{pct_diff:.1f}%", ha='center', va='center', 
            color=box_color, fontweight='bold', bbox=bbox_props, fontsize=12)
    
    ax.set_ylim(0, max_y * 1.45)
    ax.set_title(title, fontweight='bold', pad=20, fontsize=16)
    if ylabel: ax.set_ylabel(ylabel, fontweight='bold', fontsize=14)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.tick_params(axis='x', labelsize=15); ax.tick_params(axis='y', labelsize=13)
    ax.grid(axis='y', linestyle='--', alpha=0.4)

def add_figure_label(fig, label):
    fig.text(0.01, 0.98, label, fontsize=26, fontweight='bold', va='top', ha='left')

# ==================== Figure B: 频率分布 ====================
fig_b, (ax_b1, ax_b2) = plt.subplots(1, 2, figsize=(FIG_WIDTH, FIG_HEIGHT), gridspec_kw={'width_ratios': [1, 1.3]})
ax_b1.axvspan(0.05, 0.110, color='#92a8d1', alpha=0.6, label='1P Excitation')
ax_b1.axvspan(0.150, 0.330, color='#f6b0a0', alpha=0.6, label='3P Excitation')
ai_ss_f, ai_fa_f = 0.481, 0.487
tq_ss_f, tq_fa_f = 0.415, 0.424
ax_b1.axvline(x=ai_fa_f, color=color_ai, linestyle='-', linewidth=3, label=f'AI 1st FA ({ai_fa_f:.3f} Hz)')
ax_b1.axvline(x=ai_ss_f, color=color_ai, linestyle='--', linewidth=3, label=f'AI 1st SS ({ai_ss_f:.3f} Hz)')
ax_b1.axvline(x=tq_fa_f, color=color_tq, linestyle='-', linewidth=2.5, label=f'Tuqiang 1st FA ({tq_fa_f:.3f} Hz)')
ax_b1.axvline(x=tq_ss_f, color=color_tq, linestyle='--', linewidth=2.5, label=f'Tuqiang 1st SS ({tq_ss_f:.3f} Hz)')
ax_b1.set_ylim(0, 1); ax_b1.set_xlim(0.0, 0.55)
ax_b1.set_title("I. Tower Natural Frequencies vs 1P/3P", fontweight='bold', pad=20, fontsize=16)
ax_b1.set_xlabel("Frequency (Hz)", fontweight='bold', fontsize=14); ax_b1.set_ylabel("Normalized spectrum", fontweight='bold', fontsize=14)
ax_b1.spines['top'].set_visible(False); ax_b1.spines['right'].set_visible(False); ax_b1.set_yticks([])
ax_b1.legend(loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False, fontsize=12)

dofs = ['Surge', 'Sway', 'Heave', 'Roll', 'Pitch', 'Yaw']
ai_periods = [51.87, 49.87, 15.54, 21.37, 20.13, 61.11]  
tq_periods = [58.47, 58.70, 18.26, 22.86, 22.89, 75.91]  
x = np.arange(len(dofs)); width = 0.35
ax_b2.bar(x - width/2, ai_periods, width, label='AI', color=color_ai)
ax_b2.bar(x + width/2, tq_periods, width, label='Tuqiang', color=color_tq)
ax_b2.axhspan(0, 15, color='#E0E0E0', alpha=0.5, label='Wave Energy Range (Danger)')
ax_b2.set_ylabel('Natural Period (s)', fontweight='bold', fontsize=14)
ax_b2.set_title('II. Platform 6-DOF Natural Periods', fontweight='bold', pad=20, fontsize=16)
ax_b2.set_xticks(x); ax_b2.set_xticklabels(dofs, fontweight='bold', fontsize=13)
ax_b2.spines['top'].set_visible(False); ax_b2.spines['right'].set_visible(False); ax_b2.set_ylim(0, 85)
ax_b2.legend(loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=3, frameon=False, fontsize=12)

plt.tight_layout(); plt.subplots_adjust(top=0.76, wspace=0.2)
fig_b.suptitle('Structural & Platform Dynamics', fontweight='bold', fontsize=20, y=0.96, x=0.5, ha='center')
add_figure_label(fig_b, 'b')
fig_b.savefig('fig_b_unified.png', dpi=300, bbox_inches='tight')

# ==================== Figure C: 变形与运动 (发电工况 - 3子图，无 Surge 限值) ====================
fig_c, axes_c = plt.subplots(1, 3, figsize=(FIG_WIDTH, FIG_HEIGHT))
c_data = {
    'I. Surge': ({'AI': 5.10, 'Tuqiang': 6.92}, 'm', None, ''),
    'II. Pitch': ({'AI': 3.42, 'Tuqiang': 2.47}, 'deg', 5, '5°'),
    'III. Tower Top Acc': ({'AI': 1.12, 'Tuqiang': 0.82}, 'm/s²', 2.94, '2.94 m/s²')
}
for ax, (title, (data, ylabel, limit, lbl)) in zip(axes_c, c_data.items()):
    plot_nature_bar(ax, title, data, ylabel, limit, lbl)
plt.tight_layout(); plt.subplots_adjust(top=0.76, wspace=0.3)
fig_c.suptitle('Deformation & Motion (Operating DLC1.1)', fontweight='bold', fontsize=20, y=0.96, x=0.5, ha='center')
add_figure_label(fig_c, 'c')
fig_c.savefig('fig_c_unified.png', dpi=300, bbox_inches='tight')

# ==================== Figure D: 极端工况运动与加速度 (3子图，无 Surge 限值) ====================
fig_d, axes_d = plt.subplots(1, 3, figsize=(FIG_WIDTH, FIG_HEIGHT))
d_data = {
    'I. Surge': ({'AI': 12.38, 'Tuqiang': 8.53}, 'm', None, ''),
    'II. Pitch': ({'AI': 9.56, 'Tuqiang': 8.02}, 'deg', 10, '10°'),
    'III. Tower Top Acc': ({'AI': 3.22, 'Tuqiang': 3.44}, 'm/s²', 5.899, '5.89 m/s²')
}
for ax, (title, (data, ylabel, limit, lbl)) in zip(axes_d, d_data.items()):
    plot_nature_bar(ax, title, data, ylabel, limit, lbl)
plt.tight_layout(); plt.subplots_adjust(top=0.76, wspace=0.3)
fig_d.suptitle('Deformation & Motion (Extreme DLC 6.1)', fontweight='bold', fontsize=20, y=0.96, x=0.5, ha='center')
add_figure_label(fig_d, 'd')
fig_d.savefig('fig_d_unified.png', dpi=300, bbox_inches='tight')

# ==================== Figure E: 最不利工况 (结构强度 - 2子图，宽松排版) ====================
fig_e, axes_e = plt.subplots(1, 2, figsize=(FIG_WIDTH, FIG_HEIGHT))
e_data = {
    'I. Max Mooring Tension': ({'AI': 13037, 'Tuqiang': 14185}, 'kN', 20165.9, '20165.9'),
    'II. Tower Base My': ({'AI': 1372, 'Tuqiang': 1139.26}, r'MN$\cdot$m', None, '')
}
for ax, (title, (data, ylabel, limit, lbl)) in zip(axes_e, e_data.items()):
    plot_nature_bar(ax, title, data, ylabel, limit, lbl)
plt.tight_layout(); plt.subplots_adjust(top=0.76, wspace=0.45) # 进一步增大 wspace 确保双子图排版宽松美观
fig_e.suptitle('Structural Load (Extreme DLC 6.1)', fontweight='bold', fontsize=20, y=0.96, x=0.5, ha='center')
add_figure_label(fig_e, 'e')
fig_e.savefig('fig_e_unified.png', dpi=300, bbox_inches='tight')

print("All unified figures successfully saved with relaxed 2-subplot layout.")