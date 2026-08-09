import os
import logging
import pandas as pd
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

def plot_platform_distribution(df: pd.DataFrame, output_dir: str = "plots") -> str:
    """Generates and saves a bar chart of game counts per platform."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "platform_distribution.png")
    
    logger.info("Generating platform distribution plot.")
    plt.figure(figsize=(8, 5))
    
    platform_counts = df["platform"].value_counts()
    platform_counts.plot(kind="bar", color="#3498db", edgecolor="black")
    
    plt.title("Number of Games per Platform", fontsize=14, fontweight="bold")
    plt.xlabel("Platform", fontsize=12)
    plt.ylabel("Count of Games", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=300)
    plt.close()
    logger.info(f"Saved platform distribution plot to {output_path}")
    return output_path

def plot_price_vs_discount(df: pd.DataFrame, output_dir: str = "plots") -> str:
    """Generates and saves a scatter plot of Price vs. Discount Amount."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "price_vs_discount.png")
    
    logger.info("Generating price vs. discount scatter plot.")
    
    # Filter rows with price data
    plot_data = df.dropna(subset=["price"]).copy()
    
    colors = plot_data["source"].map({
        "Nintendo": "#e74c3c",      # Red
        "PlayStation": "#2980b9"   # Blue
    }).fillna("gray")
    
    plt.figure(figsize=(8, 5))
    plt.scatter(
        plot_data["price"],
        plot_data["discount_amount"],
        c=colors,
        alpha=0.75,
        edgecolors="none",
        s=60
    )
    
    plt.title("Price vs Discount Amount (Nintendo vs PlayStation)", fontsize=14, fontweight="bold")
    plt.xlabel("Price (£)", fontsize=12)
    plt.ylabel("Discount Amount (£)", fontsize=12)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=300)
    plt.close()
    logger.info(f"Saved price vs discount plot to {output_path}")
    return output_path