"""
Default code snippets for each language × execution mode combination.
"""

FULL_PROGRAM_SNIPPETS = {
    "Python": """\
# 🐍 Python - Full Program Mode
def greet(name):
    message = f"Hello, {name}!"
    return message

names = ["Alice", "Bob", "Charlie"]
for name in names:
    result = greet(name)
    print(result)
""",
    "JavaScript": """\
// 🌐 JavaScript - Full Program Mode
function greet(name) {
    const message = `Hello, ${name}!`;
    return message;
}

const names = ["Alice", "Bob", "Charlie"];
for (const name of names) {
    const result = greet(name);
    console.log(result);
}
""",
    "C": """\
/* ⚙️ C - Full Program Mode */
#include <stdio.h>

void greet(const char *name) {
    printf("Hello, %s!\\n", name);
}

int main() {
    const char *names[] = {"Alice", "Bob", "Charlie"};
    int n = 3;
    for (int i = 0; i < n; i++) {
        greet(names[i]);
    }
    return 0;
}
""",
    "C++": """\
// ⚡ C++ - Full Program Mode
#include <iostream>
#include <vector>
#include <string>
using namespace std;

string greet(const string& name) {
    return "Hello, " + name + "!";
}

int main() {
    vector<string> names = {"Alice", "Bob", "Charlie"};
    for (const auto& name : names) {
        cout << greet(name) << endl;
    }
    return 0;
}
""",
    "Java": """\
// ☕ Java - Full Program Mode
public class Main {
    static String greet(String name) {
        return "Hello, " + name + "!";
    }

    public static void main(String[] args) {
        String[] names = {"Alice", "Bob", "Charlie"};
        for (String name : names) {
            System.out.println(greet(name));
        }
    }
}
""",
}

LEETCODE_SNIPPETS = {
    "Python": """\
# 🐍 Python - LeetCode Mode  (class Solution style)
class Solution(object):
    def twoSum(self, nums, target):
        num_map = {}
        for i, num in enumerate(nums):
            complement = target - num
            if complement in num_map:
                return [num_map[complement], i]
            num_map[num] = i
""",
    "JavaScript": """\
// 🌐 JavaScript - LeetCode Mode
// Problem: Two Sum
/**
 * @param {number[]} nums
 * @param {number} target
 * @return {number[]}
 */
var twoSum = function(nums, target) {
    const seen = new Map();
    for (let i = 0; i < nums.length; i++) {
        const complement = target - nums[i];
        if (seen.has(complement)) {
            return [seen.get(complement), i];
        }
        seen.set(nums[i], i);
    }
    return [];
};

// --- Test ---
console.log(twoSum([2, 7, 11, 15], 9));  // [0, 1]
console.log(twoSum([3, 2, 4], 6));       // [1, 2]
""",
    "C": """\
/* ⚙️ C - LeetCode Mode */
/* Problem: Two Sum */
#include <stdio.h>
#include <stdlib.h>

int* twoSum(int* nums, int numsSize, int target, int* returnSize) {
    int* result = (int*)malloc(2 * sizeof(int));
    *returnSize = 2;
    for (int i = 0; i < numsSize - 1; i++) {
        for (int j = i + 1; j < numsSize; j++) {
            if (nums[i] + nums[j] == target) {
                result[0] = i;
                result[1] = j;
                return result;
            }
        }
    }
    return result;
}

int main() {
    int nums[] = {2, 7, 11, 15};
    int returnSize;
    int* res = twoSum(nums, 4, 9, &returnSize);
    printf("[%d, %d]\\n", res[0], res[1]);
    free(res);
    return 0;
}
""",
    "C++": """\
// ⚡ C++ - LeetCode Mode
// Problem: Two Sum
#include <vector>
#include <unordered_map>
#include <iostream>
using namespace std;

class Solution {
public:
    vector<int> twoSum(vector<int>& nums, int target) {
        unordered_map<int, int> seen;
        for (int i = 0; i < (int)nums.size(); i++) {
            int complement = target - nums[i];
            if (seen.count(complement)) {
                return {seen[complement], i};
            }
            seen[nums[i]] = i;
        }
        return {};
    }
};

int main() {
    Solution sol;
    vector<int> nums = {2, 7, 11, 15};
    auto res = sol.twoSum(nums, 9);
    cout << "[" << res[0] << ", " << res[1] << "]" << endl;
    return 0;
}
""",
    "Java": """\
// ☕ Java - LeetCode Mode
// Problem: Two Sum
import java.util.*;

class Solution {
    public int[] twoSum(int[] nums, int target) {
        Map<Integer, Integer> seen = new HashMap<>();
        for (int i = 0; i < nums.length; i++) {
            int complement = target - nums[i];
            if (seen.containsKey(complement)) {
                return new int[]{seen.get(complement), i};
            }
            seen.put(nums[i], i);
        }
        return new int[]{};
    }

    public static void main(String[] args) {
        Solution sol = new Solution();
        int[] result = sol.twoSum(new int[]{2, 7, 11, 15}, 9);
        System.out.println("[" + result[0] + ", " + result[1] + "]");
    }
}
""",
}

LANGUAGE_META = {
    "Python":     {"icon": "🐍", "extension": ".py",   "comment": "#"},
    "JavaScript": {"icon": "🌐", "extension": ".js",   "comment": "//"},
    "C":          {"icon": "⚙️",  "extension": ".c",    "comment": "//"},
    "C++":        {"icon": "⚡", "extension": ".cpp",  "comment": "//"},
    "Java":       {"icon": "☕", "extension": ".java", "comment": "//"},
}
