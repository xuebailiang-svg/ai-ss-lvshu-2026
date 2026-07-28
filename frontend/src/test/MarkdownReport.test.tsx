import {render, screen, within} from '@testing-library/react';
import {expect, test} from 'vitest';
import MarkdownReport from '../components/MarkdownReport';

const SAMPLE_REPORT = `# 电竞馆选址分析报告

## 一、投资决策摘要

**结论：** 谨慎推进。

## 二、评分总览与红线风险

| 维度 | 得分 | 说明 |
| --- | ---: | --- |
| 交通 | 16 | 地铁可达 |
| 租金 | 10 | 样本不足 |

> 当前未接入真实客流数据。

## 三、数据来源

数据来源：[西安市统计局](https://tjj.xa.gov.cn/)。
`;

test('renders report table, links, quote and table of contents', () => {
  render(<MarkdownReport content={SAMPLE_REPORT} showToc />);

  expect(screen.getByRole('navigation', {name: '报告目录'})).toBeInTheDocument();
  const table = screen.getByRole('table');
  expect(within(table).getByText('交通')).toBeInTheDocument();
  expect(within(table).getByText('地铁可达')).toBeInTheDocument();
  expect(screen.getByText('当前未接入真实客流数据。').closest('blockquote')).toBeInTheDocument();

  const sourceLink = screen.getByRole('link', {name: '西安市统计局'});
  expect(sourceLink).toHaveAttribute('href', 'https://tjj.xa.gov.cn/');
  expect(sourceLink).toHaveAttribute('rel', 'noreferrer');
});
