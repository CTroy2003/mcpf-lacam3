#!/usr/bin/env python3
import argparse
import pathlib
import subprocess
import tempfile
import time
import signal
import sys
import os
import json
import datetime
import shutil

# Global list to track temp files for cleanup
temp_files = []

def cleanup_temp_files():
    """Remove all temporary files"""
    for f in temp_files:
        try:
            if os.path.exists(f):
                os.unlink(f)
        except:
            pass

def signal_handler(signum, frame):
    """Handle SIGINT gracefully"""
    print("\nCaught interrupt, cleaning up...")
    cleanup_temp_files()
    sys.exit(1)

def parse_waypoint_scenario(scen_path):
    """Parse waypoint scenario file and return list of agent data"""
    agents = []
    
    with open(scen_path, 'r') as f:
        lines = f.readlines()
    
    # Skip header line if present (version 1)
    start_idx = 0
    if lines and lines[0].strip().startswith('version'):
        start_idx = 1
    
    i = start_idx
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        parts = line.split('\t')
        if len(parts) < 10:
            i += 1
            continue
            
        # Standard MAPF fields
        s_row = int(parts[4])
        s_col = int(parts[5])
        g_row = int(parts[6])
        g_col = int(parts[7])
        # parts[8] is optimal length, parts[9] is number of waypoints
        K = int(parts[9])
        
        # Parse waypoints - they should all be on the same line
        waypoints = []
        if len(parts) >= 10 + K * 2:
            waypoint_parts = parts[10:]
            
            # Extract waypoints
            for j in range(K):
                if j*2 + 1 < len(waypoint_parts):
                    wp_row = int(waypoint_parts[j*2])
                    wp_col = int(waypoint_parts[j*2 + 1])
                    waypoints.append((wp_row, wp_col))
        else:
            print(f"Warning: Not enough waypoint data for agent with {K} waypoints")
            continue
        
        agents.append({
            'start': (s_row, s_col),
            'goal': (g_row, g_col),
            'waypoints': waypoints,
            'K': K,
            'bucket_id': int(parts[0])  # Store original bucket ID
        })
        
        i += 1
    
    return agents

def get_map_dimensions(map_file):
    """Extract map dimensions from a map file"""
    try:
        with open(map_file, 'r') as f:
            lines = f.readlines()
            
        # Look for height and width lines
        height = None
        width = None
        
        for line in lines:
            line = line.strip()
            if line.startswith('height'):
                height = int(line.split()[1])
            elif line.startswith('width'):
                width = int(line.split()[1])
                
        if height is None or width is None:
            print(f"Warning: Could not parse map dimensions from {map_file}, using default 128x128")
            return 128, 128
            
        return width, height
    except Exception as e:
        print(f"Error reading map file {map_file}: {e}, using default 128x128")
        return 128, 128

def create_segment_scenario(agents, segment_idx, map_filename, map_width=128, map_height=128):
    """Create temporary scenario file for a specific segment"""
    temp_f = tempfile.NamedTemporaryFile(mode='w', suffix='.scen', delete=False)
    temp_files.append(temp_f.name)
    
    # Write header
    temp_f.write("version 1\n")
    
    for i, agent in enumerate(agents):
        # Determine start and goal for this segment
        if segment_idx == 0:
            # First segment: start -> wp1 (or goal if no waypoints)
            start = agent['start']
            goal = agent['waypoints'][0] if agent['waypoints'] else agent['goal']
        elif segment_idx <= len(agent['waypoints']):
            # Middle segments: wp(i-1) -> wp(i) or wp(last) -> goal
            start = agent['waypoints'][segment_idx - 1]
            if segment_idx == len(agent['waypoints']):
                # Last segment: last waypoint -> goal
                goal = agent['goal']
            else:
                goal = agent['waypoints'][segment_idx]
        else:
            # Agent already reached final goal, stay put
            start = agent['goal']
            goal = agent['goal']
        
        # Write scenario line: bucket map width height s_row s_col g_row g_col opt_len
        # Calculate Manhattan distance for opt_len
        opt_len = abs(start[0] - goal[0]) + abs(start[1] - goal[1])
        temp_f.write(f"{agent['bucket_id']}\t{map_filename}\t{map_width}\t{map_height}\t{start[0]}\t{start[1]}\t{goal[0]}\t{goal[1]}\t{opt_len}\n")
    
    temp_f.close()
    return temp_f.name

def run_lacam_segment(exe, map_path, scen_path, num_agents, seed, timeout):
    """Run LaCAM on a single segment"""
    # Create temporary output file
    temp_out = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    temp_files.append(temp_out.name)
    temp_out.close()
    
    cmd = [
        str(exe),
        '--map', str(map_path),
        '--scen', str(scen_path),
        '--num', str(num_agents),
        '--seed', str(seed),
        '--time_limit_sec', str(timeout),
        '--output', temp_out.name
    ]
    
    start_time = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+10)
        runtime = time.time() - start_time
        
        if result.returncode != 0:
            print(f"LaCAM failed with return code {result.returncode}")
            print(f"stdout: {result.stdout}")
            print(f"stderr: {result.stderr}")
            print(f"Command was: {' '.join(cmd)}")
            return None, runtime, None
        
        # Parse cost from YAML output file
        cost = 0
        try:
            with open(temp_out.name, 'r') as f:
                for line in f:
                    if line.startswith('soc='):
                        cost = int(line.split('=')[1].strip())
                        break
        except:
            pass
        
        return cost, runtime, temp_out.name
        
    except subprocess.TimeoutExpired:
        print(f"LaCAM timed out after {timeout} seconds")
        return None, timeout, None

def main():
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    parser = argparse.ArgumentParser(description='Run LaCAM on waypoint scenarios segment by segment')
    parser.add_argument('--exe', required=True, help='Path to LaCAM executable')
    parser.add_argument('--map', required=True, help='Path to map file')
    parser.add_argument('--scen', required=True, help='Path to waypoint scenario file')
    parser.add_argument('--num', type=int, default=None, help='Number of agents to use (default: use all agents)')
    parser.add_argument('--multi_scale', action='store_true', help='Run with agent counts 100, 200, 300, 400, 500')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument('--timeout', type=int, default=100, help='Total timeout in seconds (divided among segments)')
    parser.add_argument('--out', required=True, help='Output directory for results')
    
    args = parser.parse_args()
    
    # Create output directory
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse waypoint scenario
    try:
        agents = parse_waypoint_scenario(args.scen)
        if not agents:
            print("Error: No agents found in scenario file")
            sys.exit(1)
    except Exception as e:
        print(f"Error parsing scenario file: {e}")
        sys.exit(1)
    
    # Determine agent counts to test
    if args.multi_scale:
        agent_counts = [100, 200, 300, 400, 500]
        print(f"Running multi-scale experiments with agent counts: {agent_counts}")
    else:
        agent_counts = [args.num] if args.num is not None else [len(agents)]
        print(f"Running single experiment with {agent_counts[0]} agents")
    
    # Store results for multi-scale summary
    all_results = []
    
    for agent_count in agent_counts:
        print(f"\n{'='*60}")
        print(f"STARTING EXPERIMENT WITH {agent_count} AGENTS")
        print(f"{'='*60}")
        
        # Limit agents for this experiment
        current_agents = agents[:agent_count]
        
        # Create specific output directory for this agent count
        if args.multi_scale:
            current_out_dir = out_dir / f"exp_{agent_count}_agents"
        else:
            current_out_dir = out_dir
        current_out_dir.mkdir(parents=True, exist_ok=True)
        
        # Run experiment for this agent count
        result = run_experiment(current_agents, args, current_out_dir)
        all_results.append({
            'agent_count': agent_count,
            'result': result
        })
        
        print(f"\nCOMPLETED: {agent_count} agents - Runtime: {result['global_results']['total_runtime_ms']:.0f}ms, Cost: {result['global_results']['total_cost']}")
    
    # Generate multi-scale summary if applicable
    if args.multi_scale:
        generate_multi_scale_summary(all_results, out_dir, args)
        
        # Display summary table in console
        print(f"\n{'='*80}")
        print("MULTI-SCALE EXPERIMENT SUMMARY")
        print(f"{'='*80}")
        print("| Agents | Runtime | Total Cost | Cost/Agent | Segments | Success |")
        print("|--------|---------|------------|------------|----------|----------|")
        for exp_result in all_results:
            agent_count = exp_result['agent_count']
            result = exp_result['result']
            runtime_s = result['global_results']['total_runtime_ms'] / 1000
            total_cost = result['global_results']['total_cost']
            cost_per_agent = result['performance_metrics']['avg_cost_per_agent']
            num_segments = result['global_results']['num_segments']
            success = "✅" if result['global_results']['all_segments_solved'] else "❌"
            
            print(f"| {agent_count:>6} | {runtime_s:>6.2f}s | {total_cost:>10,} | {cost_per_agent:>9.1f} | {num_segments:>8} | {success:>7} |")
        print(f"{'='*80}")
    
    cleanup_temp_files()

def run_experiment(agents, args, out_dir):
    """Run a single experiment with the given agents"""
    # Determine maximum number of segments needed
    max_waypoints = max(len(agent['waypoints']) for agent in agents)
    num_agents = len(agents)
    num_segments = max_waypoints + 1  # 0 to max_waypoints inclusive

    # Calculate per-segment timeout (divide total timeout equally)
    per_segment_timeout = args.timeout // num_segments
    if per_segment_timeout < 1:
        per_segment_timeout = 1  # Minimum 1 second per segment

    print(f"Found {num_agents} agents with up to {max_waypoints} waypoints each")
    print(f"Total timeout: {args.timeout}s, Per-segment timeout: {per_segment_timeout}s ({num_segments} segments)")
    
    # Run segments
    total_runtime = 0
    total_cost = 0
    wall_clock_start = time.time()
    
    # Track detailed results for summary
    segment_results = []
    experiment_info = {
        'map_file': str(args.map),
        'scenario_file': str(args.scen),
        'num_agents': num_agents,
        'max_waypoints': max_waypoints,
        'total_segments': num_segments,
        'command': ' '.join(sys.argv),
        'timestamp': datetime.datetime.now().isoformat(),
        'exe_path': str(args.exe),
        'total_timeout': args.timeout,
        'per_segment_timeout': per_segment_timeout
    }
    
    try:
        for segment_idx in range(num_segments):  # 0 to max_waypoints inclusive
            print(f"\n--- Segment {segment_idx} ---")
            
            # Create temporary scenario for this segment
            map_filename = pathlib.Path(args.map).name
            # Get map dimensions from the map file
            map_width, map_height = get_map_dimensions(args.map)
            temp_scen = create_segment_scenario(agents, segment_idx, map_filename, map_width, map_height)
            
            # Run LaCAM
            cost, runtime, plan_file = run_lacam_segment(
                args.exe, args.map, temp_scen, num_agents, args.seed, per_segment_timeout
            )
            
            if cost is None:
                print(f"Segment {segment_idx} failed!")
                cleanup_temp_files()
                sys.exit(1)
            
            # Save segment plan
            segment_out = out_dir / f"segment_{segment_idx}.yaml"
            if plan_file and os.path.exists(plan_file):
                shutil.copy2(plan_file, segment_out)
                os.remove(plan_file)  # Remove the original temp file
                print(f"Saved segment plan to {segment_out}")
            
            # Parse additional metrics from segment output
            makespan = 0
            solved = False
            try:
                with open(segment_out, 'r') as f:
                    for line in f:
                        if line.startswith('makespan='):
                            makespan = int(line.split('=')[1].strip())
                        elif line.startswith('solved='):
                            solved = int(line.split('=')[1].strip()) == 1
            except:
                pass
            
            # Track segment results
            segment_result = {
                'segment_id': segment_idx,
                'cost': cost,
                'makespan': makespan,
                'runtime_ms': runtime * 1000,
                'solved': solved,
                'output_file': str(segment_out)
            }
            segment_results.append(segment_result)
            
            # Update totals
            total_runtime += runtime
            total_cost += cost
            
            print(f"seg {segment_idx}  runtime={runtime*1000:.0f}ms  cost={cost}")
    
    except Exception as e:
        print(f"Error during execution: {e}")
        cleanup_temp_files()
        sys.exit(1)
    
    finally:
        # Clean up temp files
        cleanup_temp_files()
    
    # Final summary
    wall_clock_total = time.time() - wall_clock_start
    print(f"\n--- Global Summary ---")
    print(f"Total segment runtime: {total_runtime*1000:.0f}ms")
    print(f"Total segment cost: {total_cost}")
    print(f"Wall-clock time: {wall_clock_total*1000:.0f}ms")
    
    # Generate comprehensive results summary
    max_makespan = max(seg['makespan'] for seg in segment_results) if segment_results else 0
    all_solved = all(seg['solved'] for seg in segment_results)
    
    summary = {
        'experiment_info': experiment_info,
        'global_results': {
            'total_cost': total_cost,
            'total_runtime_ms': total_runtime * 1000,
            'wall_clock_time_ms': wall_clock_total * 1000,
            'max_makespan': max_makespan,
            'num_segments': len(segment_results),
            'all_segments_solved': all_solved,
            'end_time': datetime.datetime.now().isoformat()
        },
        'segment_results': segment_results,
        'agent_summary': {
            'total_agents': num_agents,
            'max_waypoints_per_agent': max_waypoints,
            'total_waypoint_to_waypoint_transitions': sum(len(agent['waypoints']) for agent in agents),
            'total_path_segments': (max_waypoints + 1) * num_agents
        },
        'performance_metrics': {
            'avg_runtime_per_segment_ms': (total_runtime * 1000) / len(segment_results) if segment_results else 0,
            'avg_cost_per_segment': total_cost / len(segment_results) if segment_results else 0,
            'avg_cost_per_agent': total_cost / num_agents if num_agents > 0 else 0,
            'cost_efficiency': total_cost / (wall_clock_total * 1000) if wall_clock_total > 0 else 0,  # cost per ms
        }
    }
    
    # Save individual experiment summary
    summary_file = out_dir / "waypoint_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"Comprehensive results saved to {summary_file}")

    # Also save a human-readable summary
    readable_summary = out_dir / "waypoint_summary.txt"
    with open(readable_summary, 'w') as f:
        f.write("Multi-Waypoint LACAM Results Summary\n")
        f.write("=" * 40 + "\n\n")
        f.write(f"Experiment Date: {experiment_info['timestamp']}\n")
        f.write(f"Map: {experiment_info['map_file']}\n")
        f.write(f"Scenario: {experiment_info['scenario_file']}\n")
        f.write(f"Command: {experiment_info['command']}\n\n")
        
        f.write("Agent Configuration:\n")
        f.write(f"  Total Agents: {num_agents}\n")
        f.write(f"  Max Waypoints per Agent: {max_waypoints}\n")
        f.write(f"  Total Path Segments: {(max_waypoints + 1) * num_agents}\n\n")
        
        f.write("Global Results:\n")
        f.write(f"  Total Cost (SOC): {total_cost}\n")
        f.write(f"  Max Makespan: {max_makespan}\n")
        f.write(f"  Total Runtime: {total_runtime*1000:.0f}ms\n")
        f.write(f"  Wall-Clock Time: {wall_clock_total*1000:.0f}ms\n")
        f.write(f"  All Segments Solved: {all_solved}\n\n")
        
        f.write("Performance Metrics:\n")
        f.write(f"  Avg Runtime per Segment: {(total_runtime * 1000) / len(segment_results):.1f}ms\n")
        f.write(f"  Avg Cost per Segment: {total_cost / len(segment_results):.1f}\n")
        f.write(f"  Avg Cost per Agent: {total_cost / num_agents:.1f}\n\n")
        
        f.write("Segment Breakdown:\n")
        for seg in segment_results:
            f.write(f"  Segment {seg['segment_id']}: cost={seg['cost']}, makespan={seg['makespan']}, runtime={seg['runtime_ms']:.0f}ms, solved={seg['solved']}\n")
    
    print(f"Human-readable summary saved to {readable_summary}")
    
    return summary

def generate_multi_scale_summary(all_results, out_dir, args):
    """Generate a summary for multi-scale experiments."""
    summary_file = out_dir / "multi_scale_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"Multi-scale summary saved to {summary_file}")

    # Also save a human-readable summary
    readable_summary = out_dir / "multi_scale_summary.txt"
    with open(readable_summary, 'w') as f:
        f.write("Multi-Scale LACAM Results Summary\n")
        f.write("=" * 40 + "\n\n")
        f.write(f"Experiment Date: {datetime.datetime.now().isoformat()}\n")
        f.write(f"Command: {' '.join(sys.argv)}\n\n")
        
        f.write("Experiment Results Summary:\n")
        f.write("| Agents | Runtime | Total Cost | Cost/Agent | Segments | Success |\n")
        f.write("|--------|---------|------------|------------|----------|----------|\n")
        for exp_result in all_results:
            agent_count = exp_result['agent_count']
            result = exp_result['result']
            runtime_s = result['global_results']['total_runtime_ms'] / 1000
            total_cost = result['global_results']['total_cost']
            cost_per_agent = result['performance_metrics']['avg_cost_per_agent']
            num_segments = result['global_results']['num_segments']
            success = "✅" if result['global_results']['all_segments_solved'] else "❌"
            
            f.write(f"| {agent_count:>6} | {runtime_s:>6.2f}s | {total_cost:>10,} | {cost_per_agent:>9.1f} | {num_segments:>8} | {success:>7} |\n")
        
        f.write("\nDetailed Results:\n")
        for exp_result in all_results:
            f.write(f"  Agents: {exp_result['agent_count']}\n")
            f.write(f"    Total Cost: {exp_result['result']['global_results']['total_cost']}\n")
            f.write(f"    Max Makespan: {exp_result['result']['global_results']['max_makespan']}\n")
            f.write(f"    Total Runtime: {exp_result['result']['global_results']['total_runtime_ms']:.0f}ms\n")
            f.write(f"    Wall-Clock Time: {exp_result['result']['global_results']['wall_clock_time_ms']:.0f}ms\n")
            f.write(f"    All Segments Solved: {exp_result['result']['global_results']['all_segments_solved']}\n")
            f.write(f"    Num Segments: {exp_result['result']['global_results']['num_segments']}\n\n")
        
        f.write("Performance Metrics (Average across all experiments):\n")
        total_avg_runtime = sum(exp_result['result']['performance_metrics']['avg_runtime_per_segment_ms'] for exp_result in all_results) / len(all_results)
        total_avg_cost = sum(exp_result['result']['performance_metrics']['avg_cost_per_segment'] for exp_result in all_results) / len(all_results)
        total_avg_cost_per_agent = sum(exp_result['result']['performance_metrics']['avg_cost_per_agent'] for exp_result in all_results) / len(all_results)
        total_cost_efficiency = sum(exp_result['result']['performance_metrics']['cost_efficiency'] for exp_result in all_results) / len(all_results)

        f.write(f"  Avg Runtime per Segment: {total_avg_runtime:.1f}ms\n")
        f.write(f"  Avg Cost per Segment: {total_avg_cost:.1f}\n")
        f.write(f"  Avg Cost per Agent: {total_avg_cost_per_agent:.1f}\n")
        f.write(f"  Avg Cost Efficiency (cost/ms): {total_cost_efficiency:.4f}\n")
    
    print(f"Human-readable multi-scale summary saved to {readable_summary}")

if __name__ == "__main__":
    main()