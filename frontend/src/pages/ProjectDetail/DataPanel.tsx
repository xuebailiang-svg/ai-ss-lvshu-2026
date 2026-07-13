import {Button, Card, Form, Input, InputNumber, List, Space, Statistic, Tabs, Tag, message} from 'antd';
import {submitManualInput} from '../../api/data';

export default function DataPanel({projectId, dataset, quality, onRefresh}: {projectId: string; dataset: any; quality: any; onRefresh: () => void}) {
  const pois = dataset?.pois || [];
  const competitors = dataset?.competitors || [];
  const foodCount = pois.filter((item: any) => item.category === 'food').length + (dataset?.food_businesses || []).length;
  const entertainmentCount = pois.filter((item: any) => item.category === 'entertainment').length + (dataset?.entertainments || []).length;

  const submit = async (type: 'competitor' | 'rent' | 'population', values: any) => {
    try {
      await submitManualInput(projectId, {type, data: values});
      message.success('人工补充已保存');
      onRefresh();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '保存失败');
    }
  };

  return (
    <Card title="数据完整度与人工补充">
      <Space wrap size="large" style={{marginBottom: 16}}>
        <Statistic title="POI数量" value={pois.length} />
        <Statistic title="竞品数量" value={competitors.length} />
        <Statistic title="餐饮数量" value={foodCount} />
        <Statistic title="娱乐数量" value={entertainmentCount} />
      </Space>

      <Card size="small" title="缺失字段" style={{marginBottom: 16}}>
        {(quality?.missing || []).length ? (
          <Space wrap>
            {quality.missing.map((item: string) => <Tag color="orange" key={item}>{item}</Tag>)}
          </Space>
        ) : <Tag color="green">暂无明显缺失</Tag>}
      </Card>

      <Tabs
        items={[
          {
            key: 'competitor',
            label: '竞品补充',
            children: (
              <Form layout="vertical" onFinish={values => submit('competitor', values)}>
                <Form.Item name="name" label="竞品名称"><Input /></Form.Item>
                <Form.Item name="machine_count" label="机器数量"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="gpu" label="显卡"><Input /></Form.Item>
                <Form.Item name="hour_price" label="普通价格"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="occupancy_rate" label="上座率"><InputNumber min={0} max={1} step={0.05} style={{width: '100%'}} /></Form.Item>
                <Button htmlType="submit" type="primary">保存竞品补充</Button>
              </Form>
            ),
          },
          {
            key: 'rent',
            label: '租金补充',
            children: (
              <Form layout="vertical" onFinish={values => submit('rent', values)}>
                <Form.Item name="monthly_rent" label="月租金"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="area_sqm" label="面积"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="rent_per_sqm" label="元/㎡/月"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="property_fee" label="物业费"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="transfer_fee" label="转让费"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Button htmlType="submit" type="primary">保存租金补充</Button>
              </Form>
            ),
          },
          {
            key: 'population',
            label: '人口补充',
            children: (
              <Form layout="vertical" onFinish={values => submit('population', values)}>
                <Form.Item name="nearby_university_count" label="大学数量"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="nearby_school_count" label="高职/技校数量"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="nearby_apartment_count" label="公寓数量"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="nearby_residential_count" label="住宅数量"><InputNumber style={{width: '100%'}} /></Form.Item>
                <Form.Item name="target_customer_description" label="目标客群描述"><Input.TextArea rows={3} /></Form.Item>
                <Button htmlType="submit" type="primary">保存人口补充</Button>
              </Form>
            ),
          },
        ]}
      />

      <Card size="small" title="已采集竞品" style={{marginTop: 16}}>
        <List
          size="small"
          dataSource={competitors.slice(0, 5)}
          locale={{emptyText: '暂无竞品数据'}}
          renderItem={(item: any) => <List.Item>{item.name} <Tag>{item.source}</Tag></List.Item>}
        />
      </Card>
    </Card>
  );
}
