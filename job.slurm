#!/bin/bash
## NECESSARY JOB SPECIFICATIONS
#SBATCH --job-name=lacam_benchmark
#SBATCH --time=1:00:00
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=48
#SBATCH --mem=10G
#SBATCH --output=lacam_benchmark.%j
## OPTIONAL JOB SPECIFICATIONS
##SBATCH --mail-type=ALL
##SBATCH --mail-user=<MAIL_ID>

# Load the same Python module as the other job
module load Python/3.11.5

# Run the comprehensive test script
python3 comprehensive_test.py
