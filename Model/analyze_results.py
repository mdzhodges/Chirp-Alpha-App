import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

def analyze_results():
    results_dirs = glob.glob("graphs/LR_*")
    
    summary_data = []
    
    # Column mapping from validate() return values
    # 0: huber, 1: l1, 2: r2, 3: directional_accuracy, 4: up_accuracy, 5: down_accuracy, 6: rank_corr, 7: hybrid_loss, 8: r2_bulk
    cols = {
        '2': 'R2_Total',
        '3': 'Overall_Acc',
        '4': 'Up_Acc',
        '5': 'Down_Acc',
        '6': 'IC',
        '7': 'Hybrid_Loss',
        '8': 'R2_Bulk'
    }

    for d in results_dirs:
        fold_results_path = os.path.join(d, "fold_results.csv")
        if not os.path.exists(fold_results_path):
            continue
            
        try:
            # Use index_col=0 as the first column is the fold index
            df = pd.read_csv(fold_results_path, index_col=0)
            
            # Map columns to meaningful names
            df = df.rename(columns=cols)
            
            # Extract the LAST fold (most recent data)
            last_fold = df.iloc[-1]
            
            # Extract hyperparameters from directory name
            name = os.path.basename(d)
            
            row = {
                'Run': name,
                'R2_Total': last_fold.get('R2_Total', 0),
                'R2_Bulk': last_fold.get('R2_Bulk', 0),
                'IC': last_fold.get('IC', 0),
                'Up_Acc': last_fold.get('Up_Acc', 0),
                'Down_Acc': last_fold.get('Down_Acc', 0),
                'Overall_Acc': last_fold.get('Overall_Acc', 0),
                'Hybrid_Loss': last_fold.get('Hybrid_Loss', 0)
            }
            summary_data.append(row)
            
        except Exception as e:
            print(f"Error processing {d}: {e}")

    if not summary_data:
        print("No results found in graphs/ directory.")
        return

    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values('Overall_Acc', ascending=False)
    
    print("\n=== Hyperparameter Summary (LAST FOLD ONLY) ===")
    print(summary_df[['Run', 'Overall_Acc', 'Up_Acc', 'Down_Acc', 'R2_Bulk', 'IC']].to_string(index=False))

    # Visualization
    sns.set(style="whitegrid")
    metrics_to_plot = ['Overall_Acc', 'Up_Acc', 'Down_Acc', 'R2_Bulk', 'IC']
    
    fig, axes = plt.subplots(len(metrics_to_plot), 1, figsize=(12, 4 * len(metrics_to_plot)))
    
    for i, metric in enumerate(metrics_to_plot):
        sns.barplot(data=summary_df, x='Run', y=metric, ax=axes[i], palette="viridis")
        axes[i].set_title(f'Last Fold: {metric}', fontsize=14)
        axes[i].tick_params(axis='x', rotation=45)

    plt.tight_layout()
    plt.savefig("hyperparameter_comparison_last_fold.png")
    print("\nComparison plot saved to hyperparameter_comparison_last_fold.png")
    
    # Save CSV
    summary_df.to_csv("hyperparameter_summary_processed.csv", index=False)
    print("Summary CSV saved to hyperparameter_summary_processed.csv")

if __name__ == "__main__":
    analyze_results()
