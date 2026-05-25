from components.runtime_executor import run_cpp

code = '''class Solution {
public:
    int singleNumber(vector<int>& nums) {
        int result = 0;
        for (int n : nums) result ^= n;
        return result;
    }
};'''

result = run_cpp(code, user_inputs={'nums': '[2,2,1]'})
print('compile_ok:', result.compile_ok)
print('compile_err:', result.compile_err[:100] if result.compile_err else 'none')
print('stdout:', result.stdout.strip())
print('steps:', len(result.timeline))
for s in result.timeline[:8]:
    print('  step', s['step'], 'line=', s['line'], 'vars=', list(s['variables'].items())[:3])
