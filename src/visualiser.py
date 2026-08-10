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

def plot_price_analysis(df: pd.DataFrame, output_dir: str = "plots") -> str:
    """Generates the 2-subplot comparison: Ranked Price Index and Price Distribution."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "price_analysis.png")
    
    logger.info("Generating ranked price and distribution analysis plot.")
    
    ps_df = df[df["source"] == "PlayStation"].dropna(subset=["price"]).sort_values("price").reset_index(drop=True)
    nt_df = df[df["source"] == "Nintendo"].dropna(subset=["price"]).sort_values("price").reset_index(drop=True)

    ps_df["price_rank"] = ps_df.index
    nt_df["price_rank"] = nt_df.index

    plt.figure(figsize=(14, 6))

    # Subplot 1: Ranked Price Index Scatter
    plt.subplot(1, 2, 1)
    if not ps_df.empty:
        plt.scatter(ps_df["price_rank"], ps_df["price"], label="PlayStation", alpha=0.75, color="#2980b9", s=40)
    if not nt_df.empty:
        plt.scatter(nt_df["price_rank"], nt_df["price"], label="Nintendo", alpha=0.75, color="#e74c3c", s=40)

    plt.title("Game Prices by Ranked Index (PS vs Nintendo)", fontsize=13, fontweight="bold")
    plt.xlabel("Price Rank (Low to High)", fontsize=11)
    plt.ylabel("Price (£)", fontsize=11)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()

    # Subplot 2: Price Distribution Histogram
    plt.subplot(1, 2, 2)
    if not ps_df.empty:
        plt.hist(ps_df["price"], bins=15, alpha=0.6, label="PlayStation", color="#2980b9", edgecolor="black")
    if not nt_df.empty:
        plt.hist(nt_df["price"], bins=15, alpha=0.6, label="Nintendo", color="#e74c3c", edgecolor="black")

    plt.title("Price Distribution Comparison", fontsize=13, fontweight="bold")
    plt.xlabel("Price (£)", fontsize=11)
    plt.ylabel("Frequency", fontsize=11)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    logger.info(f"Saved price analysis plot to {output_path}")
    return output_path

def plot_price_vs_discount(df: pd.DataFrame, output_dir: str = "plots") -> str:
    """Generates and saves a scatter plot of Price vs. Discount Amount for discounted games."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "price_vs_discount.png")
    
    logger.info("Generating price vs. discount scatter plot.")
    
    # Filter rows that have both a price and a discount
    discounted_df = df.dropna(subset=["price", "discount_amount"]).copy()
    
    ps_deals = discounted_df[discounted_df["source"] == "PlayStation"]
    nt_deals = discounted_df[discounted_df["source"] == "Nintendo"]
    
    plt.figure(figsize=(9, 5.5))
    
    if not ps_deals.empty:
        plt.scatter(
            ps_deals["price"],
            ps_deals["discount_amount"],
            c="#2980b9",
            label="PlayStation",
            alpha=0.75,
            edgecolors="black",
            linewidths=0.5,
            s=60
        )
    if not nt_deals.empty:
        plt.scatter(
            nt_deals["price"],
            nt_deals["discount_amount"],
            c="#e74c3c",
            label="Nintendo",
            alpha=0.75,
            edgecolors="black",
            linewidths=0.5,
            s=60
        )
    
    plt.title("Price vs Discount Amount (On-Sale Titles)", fontsize=13, fontweight="bold")
    plt.xlabel("Current Price (£)", fontsize=11)
    plt.ylabel("Discount Amount (£)", fontsize=11)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=300)
    plt.close()
    logger.info(f"Saved price vs discount plot to {output_path}")
    return output_path