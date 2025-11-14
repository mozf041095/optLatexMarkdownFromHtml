import re
import argparse
import requests

"""从指定URL下载HTML内容"""
def download_html_from_url(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"下载网页失败: {e}")
        return None

"""处理表格结构，确保Markdown表格正确渲染"""
def process_tables(content):
    # 匹配Markdown表格（包含表头分隔线| --- | --- |）
    table_pattern = re.compile(
        r'(?P<table>(?:\|.*?\|[\r\n]+)+)',  # 表格内容
        re.DOTALL | re.MULTILINE
    )
    
    def replace_table(match):
        table_content = match.group('table')
        lines = [line.strip() for line in table_content.split('\n') if line.strip()]
        
        # 构建HTML表格
        html_table = []
        html_table.append('<table class="markdown-table">')
        html_table.append('<thead>')
        # 保留表头中的公式结构，不破坏下划线
        header = lines[0].replace("|", "</td><td>").replace("<td>", "", 1).replace("</td>", "", 1)
        html_table.append(f'  <tr>{header}</tr>')
        html_table.append('</thead>')
        html_table.append('<tbody>')
        
        # 处理内容行，保护公式中的下划线
        for line in lines[2:]:
            if '|' in line:
                row = line.replace("|", "</td><td>").replace("<td>", "", 1).replace("</td>", "", 1)
                html_table.append(f'  <tr>{row}</tr>')
        
        html_table.append('</tbody>')
        html_table.append('</table>')
        
        return '\n'.join(html_table)
    
    # 先处理表格，避免后续处理破坏表格结构
    content = table_pattern.sub(replace_table, content)
    
    # 添加表格样式
    table_css = """
    <style>
    .markdown-table {
        border-collapse: collapse;
        width: 100%;
        margin: 1.5em 0;
        border: 1px solid #ddd;
    }
    .markdown-table th, .markdown-table td {
        padding: 0.8em 1em;
        text-align: left;
        border-bottom: 1px solid #ddd;
    }
    .markdown-table th {
        background-color: #f5f5f5;
        font-weight: bold;
    }
    .markdown-table tr:hover {
        background-color: #f9f9f9;
    }
    </style>
    """
    
    # 将样式插入到<head>标签
    if re.search(r'</head>', content, flags=re.IGNORECASE):
        content = re.sub(
            r'(</head>)',
            f'{table_css}\n\\1',
            content,
            flags=re.IGNORECASE
        )
    return content

"""优化公式中的下标显示，确保下划线正确处理"""
def fix_subscript_equations(content):
    # 1. 保护公式中的下划线，避免被空格分割
    # 匹配公式中的\alpha_t、\mu_\theta等模式，确保下划线前后无多余空格
    subscript_pattern = re.compile(r'([a-zA-Z\\]+)_\s*([a-zA-Z0-9_]+)')
    content = subscript_pattern.sub(r'\1_\2', content)  # 移除下划线前后的空格
    
    # 2. 处理被错误分割的下标（如因HTML标签导致的分割）
    # 匹配类似\mu_ <em>t</em>的错误格式
    broken_subscript_pattern = re.compile(r'([a-zA-Z\\]+)_\s*</?em>\s*([a-zA-Z0-9_]+)\s*</?em>')
    content = broken_subscript_pattern.sub(r'\1_\2', content)
    
    # 3. 处理表格中被<td>分割的下标
    table_subscript_pattern = re.compile(r'([a-zA-Z\\]+)_</?td>\s*<td>\s*([a-zA-Z0-9_]+)')
    content = table_subscript_pattern.sub(r'\1_\2', content)
    
    return content

"""处理被分割的公式，合并为完整公式并保护下标"""
def merge_separated_equations(content):
    # 先修复下标问题
    content = fix_subscript_equations(content)
    
    # 1. 处理表格标签<td>和强调标签<em>及其闭合标签
    content = re.sub(
        r'\s*<\/?(td|em)>\s*',
        ' ', 
        content, 
        flags=re.IGNORECASE | re.DOTALL
    )
    
    # 2. 标记所有公式块（$$...$$）
    block_placeholder = "___BLOCK_EQUATION___"
    block_pattern = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
    block_matches = block_pattern.findall(content)
    content = block_pattern.sub(block_placeholder, content)
    
    # 3. 标记行内公式（$...$）
    inline_placeholder = "___INLINE_EQUATION___"
    inline_pattern = re.compile(r'(?<!\$)\$(.*?)\$(?!\$)', re.DOTALL)
    inline_matches = inline_pattern.findall(content)
    content = inline_pattern.sub(inline_placeholder, content)
    
    # 4. 恢复公式块并清理内部空白，保护下标
    for match in block_matches:
        # 仅移除多余空行，保留必要的空格
        cleaned_match = re.sub(r'\n+', '\n', match.strip())
        cleaned_match = re.sub(r' +', ' ', cleaned_match)
        content = content.replace(block_placeholder, f'$$\n{cleaned_match}\n$$', 1)
    
    # 5. 恢复行内公式并清理内部空白，保护下标
    for match in inline_matches:
        cleaned_match = re.sub(r' +', ' ', match.strip())
        content = content.replace(inline_placeholder, f'${cleaned_match}$', 1)
    
    # 6. 最终检查并修复可能遗漏的下标空格
    content = fix_subscript_equations(content)
    
    return content

"""处理HTML内容：替换公式并添加MathJax配置，重点优化下标显示"""
def process_html_content(content):
    # 第一步：优先处理表格，避免公式处理影响表格结构
    content = process_tables(content)
    
    # 第二步：合并分割的公式，重点保护下标
    content = merge_separated_equations(content)
    
    # 第三步：处理块级公式（$$...$$）
    block_placeholder = "___BLOCK_EQUATION___"
    block_pattern = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
    block_matches = block_pattern.findall(content)
    content = block_pattern.sub(block_placeholder, content)
    
    # 第四步：处理行内公式（$...$）
    inline_pattern = re.compile(r'(?<!\$)\$(.*?)\$(?!\$)')
    content = inline_pattern.sub(r'\\(\1\\)', content)
    
    # 第五步：恢复块级公式并规范格式，确保下标正确
    for match in block_matches:
        cleaned_match = match.strip()
        content = content.replace(block_placeholder, f'\\[\n{cleaned_match}\n\\]', 1)
    
    # 第六步：配置MathJax，确保正确解析下标
    mathjax_config = """
    <script>
        MathJax.config = {
            tex: {
                inlineMath: [['\\\\(', '\\\\)']],
                displayMath: [['\\\\[', '\\\\]']],
                processEscapes: true,
                processEnvironments: true,
                // 确保下划线正确解析为下标
                macros: {
                    // 可以在这里定义常用宏，但主要确保默认解析正确
                }
            },
            svg: {
                fontCache: 'global'
            }
        };
    </script>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    """
    
    # 插入MathJax配置
    if re.search(r'</head>', content, flags=re.IGNORECASE):
        modified_content = re.sub(
            r'(</head>)', 
            f'{mathjax_config}\n\\1',
            content, 
            flags=re.IGNORECASE
        )
    elif re.search(r'<html>', content, flags=re.IGNORECASE):
        modified_content = re.sub(
            r'(<html>)', 
            f'\\1\n<head>\n{mathjax_config}\n</head>',
            content, 
            flags=re.IGNORECASE
        )
    else:
        modified_content = f'<head>\n{mathjax_config}\n</head>\n' + content
    
    return modified_content

def get_filename_from_url(url):
    if '/' in url:
        filename = url.split('/')[-1]
        if '.' in filename:
            return filename
    return 'chapter.html'

def main():
    parser = argparse.ArgumentParser(description='处理含公式和表格的HTML并优化下标显示')
    parser.add_argument('url', help='要下载的网页URL')
    args = parser.parse_args()
    
    print(f"正在从 {args.url} 下载网页...")
    html_content = download_html_from_url(args.url)
    if not html_content:
        return
    
    print("正在处理网页内容...")
    processed_content = process_html_content(html_content)
    
    output_filename = get_filename_from_url(args.url)
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(processed_content)
    
    print(f"处理完成，结果已保存到 {output_filename}")

if __name__ == "__main__":
    main()
