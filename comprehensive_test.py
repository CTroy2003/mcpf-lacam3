#!/usr/bin/env python3

import os
import sys
import subprocess
import pathlib
import json
import datetime
import time
import argparse
from typing import List, Dict, Any

class ComprehensiveTestRunner:
    def __init__(self, base_dir: str = "."):
        self.base_dir = pathlib.Path(base_dir)
        self.maps_dir = self.base_dir / "scripts" / "map"
        self.scenarios_dir = self.base_dir / "scripts" / "scen"
        self.results_dir = self.base_dir / "results" / "comprehensive"
        self.lacam_script = self.base_dir / "lacam.py"
        self.exe_path = self.base_dir / "build" / "main"
        
        # Test configuration
        self.agent_counts = [100, 200, 300, 400, 500]
        self.waypoint_configs = [
            {"waypoints": 2, "suffix": "1"},
            {"waypoints": 4, "suffix": "2"},
            {"waypoints": 8, "suffix": "3"}
        ]
        
        # Map configurations - (scenario_dir_name, map_file_name)
        self.maps = [
            {"scen_dir": "ost003d", "map_file": "ost003d"},
            {"scen_dir": "maze-128-128-10", "map_file": "maze-128-128-10"},
            {"scen_dir": "warehouse-20-40-10", "map_file": "warehouse-20-40-10-2-1"}
        ]
        
        self.all_results = []
        
    def ensure_directories(self):
        """Create necessary directories if they don't exist"""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
    def check_prerequisites(self):
        """Check that all required files exist"""
        missing_files = []
        
        if not self.lacam_script.exists():
            missing_files.append(str(self.lacam_script))
        if not self.exe_path.exists():
            missing_files.append(str(self.exe_path))
            
        # Check maps
        for map_config in self.maps:
            map_file = self.maps_dir / f"{map_config['map_file']}.map"
            if not map_file.exists():
                missing_files.append(str(map_file))
                
        # Check scenario files
        for map_config in self.maps:
            scenario_dir = self.scenarios_dir / map_config['scen_dir']
            if not scenario_dir.exists():
                missing_files.append(str(scenario_dir))
                continue
                
            for wp_config in self.waypoint_configs:
                scenario_file = scenario_dir / f"{map_config['map_file']}-random-{wp_config['suffix']}.scen"
                if not scenario_file.exists():
                    missing_files.append(str(scenario_file))
                
        if missing_files:
            print("❌ Missing required files:")
            for file in missing_files:
                print(f"  - {file}")
            return False
            
        return True
        
    def run_single_experiment(self, map_config: Dict[str, Any], wp_config: Dict[str, Any], agent_count: int) -> Dict[str, Any]:
        """Run a single experiment configuration"""
        map_name = map_config['map_file']
        waypoints = wp_config["waypoints"]
        suffix = wp_config["suffix"]
        
        print(f"\n🚀 Running: {map_name} | {waypoints}wp | {agent_count} agents")
        
        # Paths
        map_file = self.maps_dir / f"{map_name}.map"
        scenario_file = self.scenarios_dir / map_config['scen_dir'] / f"{map_name}-random-{suffix}.scen"
        output_dir = self.results_dir / f"{map_name}_{waypoints}wp_{agent_count}agents"
        
        # Run the experiment
        cmd = [
            "python3", str(self.lacam_script),
            "--exe", str(self.exe_path),
            "--map", str(map_file),
            "--scen", str(scenario_file),
            "--num", str(agent_count),
            "--out", str(output_dir)
        ]
        
        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 min timeout
            end_time = time.time()
            
            if result.returncode == 0:
                # Parse results from the output directory
                summary_file = output_dir / "waypoint_summary.json"
                if summary_file.exists():
                    with open(summary_file, 'r') as f:
                        summary_data = json.load(f)
                        
                    return {
                        'map': map_name,
                        'waypoints': waypoints,
                        'agent_count': agent_count,
                        'status': 'success',
                        'wall_time': end_time - start_time,
                        'data': summary_data
                    }
                else:
                    return {
                        'map': map_name,
                        'waypoints': waypoints,
                        'agent_count': agent_count,
                        'status': 'no_summary',
                        'wall_time': end_time - start_time,
                        'error': 'Summary file not found'
                    }
            else:
                return {
                    'map': map_name,
                    'waypoints': waypoints,
                    'agent_count': agent_count,
                    'status': 'failed',
                    'wall_time': end_time - start_time,
                    'error': result.stderr,
                    'stdout': result.stdout
                }
                
        except subprocess.TimeoutExpired:
            return {
                'map': map_name,
                'waypoints': waypoints,
                'agent_count': agent_count,
                'status': 'timeout',
                'wall_time': 300,
                'error': 'Experiment timed out after 5 minutes'
            }
        except Exception as e:
            return {
                'map': map_name,
                'waypoints': waypoints,
                'agent_count': agent_count,
                'status': 'error',
                'wall_time': time.time() - start_time,
                'error': str(e)
            }
            
    def run_all_experiments(self):
        """Run all experiment combinations"""
        total_experiments = len(self.maps) * len(self.waypoint_configs) * len(self.agent_counts)
        experiment_count = 0
        
        print(f"\n🎯 Starting comprehensive testing: {total_experiments} experiments")
        print(f"Maps: {[m['map_file'] for m in self.maps]}")
        print(f"Waypoint configs: {[f'{wp['waypoints']}wp' for wp in self.waypoint_configs]}")
        print(f"Agent counts: {self.agent_counts}")
        
        start_time = time.time()
        
        for map_config in self.maps:
            for wp_config in self.waypoint_configs:
                for agent_count in self.agent_counts:
                    experiment_count += 1
                    print(f"\n{'='*60}")
                    print(f"EXPERIMENT {experiment_count}/{total_experiments}")
                    print(f"{'='*60}")
                    
                    result = self.run_single_experiment(map_config, wp_config, agent_count)
                    self.all_results.append(result)
                    
                    # Print immediate result
                    if result['status'] == 'success':
                        cost = result['data']['global_results']['total_cost']
                        runtime = result['data']['global_results']['total_runtime_ms']
                        print(f"✅ SUCCESS: Cost={cost:,}, Runtime={runtime:.0f}ms")
                    else:
                        print(f"❌ FAILED: {result['status']}")
                        if result.get('error'):
                            print(f"   Error: {result['error'][:100]}...")
                        if result.get('stdout'):
                            print(f"   Stdout: {result['stdout'][:100]}...")
                        
        total_time = time.time() - start_time
        print(f"\n🎉 All experiments completed in {total_time:.1f} seconds")
        
    def generate_comprehensive_report(self):
        """Generate a comprehensive report of all results"""
        report_file = self.results_dir / "comprehensive_report.json"
        summary_file = self.results_dir / "comprehensive_summary.txt"
        
        # Save raw results
        with open(report_file, 'w') as f:
            json.dump(self.all_results, f, indent=2)
            
        # Generate summary report
        with open(summary_file, 'w') as f:
            f.write("COMPREHENSIVE LACAM TESTING REPORT\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Generated: {datetime.datetime.now().isoformat()}\n")
            f.write(f"Total Experiments: {len(self.all_results)}\n\n")
            
            # Success rate
            successful = sum(1 for r in self.all_results if r['status'] == 'success')
            f.write(f"Success Rate: {successful}/{len(self.all_results)} ({successful/len(self.all_results)*100:.1f}%)\n\n")
            
            # Results table
            f.write("RESULTS SUMMARY\n")
            f.write("-" * 100 + "\n")
            f.write(f"{'Map':<20} {'WP':<3} {'Agents':<7} {'Status':<10} {'Runtime':<10} {'Cost':<12} {'Cost/Agent':<12}\n")
            f.write("-" * 100 + "\n")
            
            for result in self.all_results:
                map_name = result['map'][:19]
                waypoints = result['waypoints']
                agent_count = result['agent_count']
                status = result['status'][:9]
                
                if result['status'] == 'success':
                    runtime = f"{result['data']['global_results']['total_runtime_ms']:.0f}ms"
                    cost = result['data']['global_results']['total_cost']
                    cost_per_agent = f"{result['data']['performance_metrics']['avg_cost_per_agent']:.1f}"
                    cost_str = f"{cost:,}"
                else:
                    runtime = "N/A"
                    cost_str = "N/A"
                    cost_per_agent = "N/A"
                    
                f.write(f"{map_name:<20} {waypoints:<3} {agent_count:<7} {status:<10} {runtime:<10} {cost_str:<12} {cost_per_agent:<12}\n")
                
            # Performance analysis by map
            f.write("\n\nPERFORMANCE ANALYSIS BY MAP\n")
            f.write("-" * 50 + "\n")
            
            for map_config in self.maps:
                map_name = map_config['map_file']
                map_results = [r for r in self.all_results if r['map'] == map_name and r['status'] == 'success']
                if map_results:
                    f.write(f"\n{map_name}:\n")
                    for wp_config in self.waypoint_configs:
                        waypoints = wp_config['waypoints']
                        wp_results = [r for r in map_results if r['waypoints'] == waypoints]
                        if wp_results:
                            avg_cost_per_agent = sum(r['data']['performance_metrics']['avg_cost_per_agent'] for r in wp_results) / len(wp_results)
                            avg_runtime = sum(r['data']['global_results']['total_runtime_ms'] for r in wp_results) / len(wp_results)
                            f.write(f"  {waypoints}wp: Avg cost/agent={avg_cost_per_agent:.1f}, Avg runtime={avg_runtime:.0f}ms\n")
                
        print(f"📊 Comprehensive report saved to: {report_file}")
        print(f"📋 Summary report saved to: {summary_file}")
        
    def run(self):
        """Main execution method"""
        print("🚀 LACAM Comprehensive Testing Framework")
        print("=" * 50)
        
        if not self.check_prerequisites():
            return False
            
        self.ensure_directories()
        self.run_all_experiments()
        self.generate_comprehensive_report()
        
        return True

def main():
    parser = argparse.ArgumentParser(description='Run comprehensive LACAM testing across all maps and configurations')
    parser.add_argument('--base_dir', default='.', help='Base directory for the project')
    
    args = parser.parse_args()
    
    runner = ComprehensiveTestRunner(args.base_dir)
    success = runner.run()
    
    if success:
        print("\n🎉 Comprehensive testing completed successfully!")
    else:
        print("\n❌ Comprehensive testing failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 