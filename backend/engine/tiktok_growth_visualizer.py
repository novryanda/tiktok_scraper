# ============================================================
# TIKTOK GROWTH VISUALIZER — Grafik Pertumbuhan
# ============================================================
# Membuat grafik visual dari tracking data
# ============================================================

import os
import json
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from colorama import Fore, init

init(autoreset=True)

OUTPUT_DIR = "output_tiktok_profiles"
TRACKING_FILE = os.path.join(OUTPUT_DIR, "growth_tracking.json")


class TikTokGrowthVisualizer:
    
    def __init__(self):
        self.tracking_data = self._load_tracking_data()
    
    def _load_tracking_data(self):
        """Load tracking data dari file"""
        if not os.path.exists(TRACKING_FILE):
            print(Fore.RED + f"❌ Tracking file tidak ditemukan: {TRACKING_FILE}")
            print(Fore.YELLOW + "   Jalankan tiktok_profile_scraper.py dulu untuk scrape profil")
            return {}
        
        with open(TRACKING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def list_tracked_users(self):
        """List semua user yang ada di tracking"""
        if not self.tracking_data:
            print(Fore.YELLOW + "Belum ada data tracking")
            return []
        
        print(Fore.CYAN + "\n📊 User yang ter-track:")
        users = []
        for username, data in self.tracking_data.items():
            count = len(data.get("history", []))
            first = data.get("first_tracked", "")
            last = data.get("last_tracked", "")
            
            if first:
                first_date = datetime.fromisoformat(first).strftime("%d %b %Y")
            else:
                first_date = "-"
            
            if last:
                last_date = datetime.fromisoformat(last).strftime("%d %b %Y")
            else:
                last_date = "-"
            
            print(f"  • @{username} ({count} data points) — {first_date} to {last_date}")
            users.append(username)
        
        return users
    
    def plot_growth(self, username: str, metrics: list = None, save_file: str = None):
        """
        Plot grafik pertumbuhan
        
        Args:
            username: Username TikTok (tanpa @)
            metrics: List metrics yang mau di-plot ['followers', 'following', 'likes', 'videos']
                     Default: ['followers', 'following']
            save_file: Path untuk save grafik (None = tampilkan saja)
        """
        username = username.strip().lstrip('@')
        
        if username not in self.tracking_data:
            print(Fore.RED + f"❌ Tidak ada data untuk @{username}")
            return
        
        if metrics is None:
            metrics = ['followers', 'following']
        
        history = self.tracking_data[username]["history"]
        
        if len(history) < 2:
            print(Fore.YELLOW + f"⚠️  Hanya ada {len(history)} data point, perlu minimal 2")
            return
        
        # Parse data
        dates = []
        data_dict = {
            'followers': [],
            'following': [],
            'likes': [],
            'videos': [],
        }
        
        for entry in history:
            date = datetime.fromisoformat(entry["scraped_at"])
            dates.append(date)
            data_dict['followers'].append(entry.get("followers", 0))
            data_dict['following'].append(entry.get("following", 0))
            data_dict['likes'].append(entry.get("total_likes", 0))
            data_dict['videos'].append(entry.get("total_videos", 0))
        
        # Create plot
        num_metrics = len(metrics)
        fig, axes = plt.subplots(num_metrics, 1, figsize=(12, 4 * num_metrics))
        
        # Jika hanya 1 metric, axes bukan array
        if num_metrics == 1:
            axes = [axes]
        
        fig.suptitle(f'TikTok Growth Analysis — @{username}', fontsize=16, fontweight='bold')
        
        metric_labels = {
            'followers': '👥 Followers',
            'following': '👤 Following',
            'likes': '❤️ Total Likes',
            'videos': '🎬 Videos',
        }
        
        metric_colors = {
            'followers': '#FF0050',  # TikTok pink
            'following': '#00F2EA',  # TikTok cyan
            'likes': '#FE2C55',      # Red
            'videos': '#25F4EE',     # Bright cyan
        }
        
        for idx, metric in enumerate(metrics):
            ax = axes[idx]
            
            # Plot line
            ax.plot(dates, data_dict[metric], 
                   marker='o', 
                   linestyle='-', 
                   linewidth=2, 
                   markersize=6,
                   color=metric_colors.get(metric, '#000000'),
                   label=metric_labels.get(metric, metric))
            
            # Fill area
            ax.fill_between(dates, data_dict[metric], alpha=0.3, color=metric_colors.get(metric, '#000000'))
            
            # Grid
            ax.grid(True, alpha=0.3, linestyle='--')
            
            # Labels
            ax.set_ylabel(metric_labels.get(metric, metric), fontsize=12, fontweight='bold')
            ax.legend(loc='upper left')
            
            # Format y-axis
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
            
            # Format x-axis
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b %Y'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            
            # Rotate x labels
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
            
            # Show growth
            if len(data_dict[metric]) >= 2:
                first_val = data_dict[metric][0]
                last_val = data_dict[metric][-1]
                growth = last_val - first_val
                growth_pct = (growth / first_val * 100) if first_val > 0 else 0
                
                # Add text annotation
                color = 'green' if growth >= 0 else 'red'
                sign = '+' if growth >= 0 else ''
                ax.text(0.02, 0.98, 
                       f'Growth: {sign}{growth:,} ({sign}{growth_pct:.1f}%)',
                       transform=ax.transAxes,
                       fontsize=10,
                       verticalalignment='top',
                       bbox=dict(boxstyle='round', facecolor=color, alpha=0.2))
        
        # Last axis: add date label
        axes[-1].set_xlabel('Date', fontsize=12, fontweight='bold')
        
        plt.tight_layout()
        
        # Save or show
        if save_file:
            plt.savefig(save_file, dpi=300, bbox_inches='tight')
            print(Fore.GREEN + f"\n📊 Grafik tersimpan: {save_file}")
        else:
            print(Fore.CYAN + "\n📊 Menampilkan grafik...")
            plt.show()
        
        plt.close()
    
    def plot_comparison(self, usernames: list, metric: str = 'followers', save_file: str = None):
        """
        Plot comparison beberapa user
        
        Args:
            usernames: List username untuk dibandingkan
            metric: Metric yang mau dibandingkan ('followers', 'following', 'likes', 'videos')
            save_file: Path untuk save grafik
        """
        fig, ax = plt.subplots(figsize=(14, 7))
        
        colors = ['#FF0050', '#00F2EA', '#FE2C55', '#25F4EE', '#000000', '#888888']
        
        for idx, username in enumerate(usernames):
            username = username.strip().lstrip('@')
            
            if username not in self.tracking_data:
                print(Fore.YELLOW + f"⚠️  Skip @{username} (tidak ada data)")
                continue
            
            history = self.tracking_data[username]["history"]
            
            # Parse data
            dates = []
            values = []
            
            for entry in history:
                date = datetime.fromisoformat(entry["scraped_at"])
                dates.append(date)
                
                if metric == 'followers':
                    values.append(entry.get("followers", 0))
                elif metric == 'following':
                    values.append(entry.get("following", 0))
                elif metric == 'likes':
                    values.append(entry.get("total_likes", 0))
                elif metric == 'videos':
                    values.append(entry.get("total_videos", 0))
            
            # Plot
            color = colors[idx % len(colors)]
            ax.plot(dates, values, 
                   marker='o', 
                   linestyle='-', 
                   linewidth=2,
                   markersize=5,
                   color=color,
                   label=f'@{username}',
                   alpha=0.8)
        
        # Styling
        metric_labels = {
            'followers': '👥 Followers',
            'following': '👤 Following',
            'likes': '❤️ Total Likes',
            'videos': '🎬 Videos',
        }
        
        ax.set_title(f'TikTok Comparison — {metric_labels.get(metric, metric)}', 
                    fontsize=16, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12, fontweight='bold')
        ax.set_ylabel(metric_labels.get(metric, metric), fontsize=12, fontweight='bold')
        
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(loc='best', fontsize=10)
        
        # Format axes
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b %Y'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        
        # Save or show
        if save_file:
            plt.savefig(save_file, dpi=300, bbox_inches='tight')
            print(Fore.GREEN + f"\n📊 Comparison chart tersimpan: {save_file}")
        else:
            print(Fore.CYAN + "\n📊 Menampilkan comparison chart...")
            plt.show()
        
        plt.close()
    
    def run_interactive(self):
        """Interactive mode"""
        print(Fore.CYAN + "\n" + "=" * 70)
        print(Fore.CYAN + "  TIKTOK GROWTH VISUALIZER")
        print(Fore.CYAN + "=" * 70)
        
        if not self.tracking_data:
            return
        
        while True:
            print(Fore.CYAN + "\n📊 MENU")
            print("  1. List tracked users")
            print("  2. Plot single user growth")
            print("  3. Plot comparison (multiple users)")
            print("  4. Exit")
            
            choice = input(Fore.WHITE + "\nPilih [1-4]: ").strip()
            
            if choice == "1":
                self.list_tracked_users()
            
            elif choice == "2":
                users = self.list_tracked_users()
                if not users:
                    continue
                
                username = input("\n👤 Username: ").strip()
                
                print("\n📊 Pilih metrics (pisahkan dengan koma):")
                print("  1. followers")
                print("  2. following")
                print("  3. likes")
                print("  4. videos")
                print("  5. all (semua)")
                
                metrics_input = input("\nMetrics [1,2 atau all]: ").strip().lower()
                
                if metrics_input == "all" or metrics_input == "5":
                    metrics = ['followers', 'following', 'likes', 'videos']
                else:
                    metric_map = {
                        '1': 'followers',
                        '2': 'following',
                        '3': 'likes',
                        '4': 'videos',
                    }
                    metrics = [metric_map[m.strip()] for m in metrics_input.split(',') if m.strip() in metric_map]
                
                if not metrics:
                    metrics = ['followers', 'following']
                
                save = input("\n💾 Save grafik? (y/n) [n]: ").strip().lower()
                save_file = None
                if save == 'y':
                    save_file = os.path.join(OUTPUT_DIR, f"growth_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                
                self.plot_growth(username, metrics, save_file)
            
            elif choice == "3":
                users = self.list_tracked_users()
                if not users:
                    continue
                
                usernames = input("\n👥 Usernames (pisahkan dengan koma): ").strip().split(',')
                usernames = [u.strip() for u in usernames if u.strip()]
                
                if not usernames:
                    print(Fore.RED + "❌ Tidak ada username yang valid")
                    continue
                
                print("\n📊 Metric untuk comparison:")
                print("  1. followers")
                print("  2. following")
                print("  3. likes")
                print("  4. videos")
                
                metric_choice = input("\nPilih [1-4] [1]: ").strip()
                metric_map = {
                    '1': 'followers',
                    '2': 'following',
                    '3': 'likes',
                    '4': 'videos',
                }
                metric = metric_map.get(metric_choice, 'followers')
                
                save = input("\n💾 Save grafik? (y/n) [n]: ").strip().lower()
                save_file = None
                if save == 'y':
                    save_file = os.path.join(OUTPUT_DIR, f"comparison_{metric}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                
                self.plot_comparison(usernames, metric, save_file)
            
            elif choice == "4":
                print(Fore.CYAN + "\n👋 Bye!")
                break
            else:
                print(Fore.RED + "❌ Pilihan tidak valid")


if __name__ == "__main__":
    visualizer = TikTokGrowthVisualizer()
    visualizer.run_interactive()