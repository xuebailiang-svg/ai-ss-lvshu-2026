import '@testing-library/jest-dom/vitest';
import '@ant-design/v5-patch-for-react-19';

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

window.getComputedStyle = () => ({
  width: '1024px',
  height: '768px',
  paddingLeft: '0px',
  paddingRight: '0px',
  paddingTop: '0px',
  paddingBottom: '0px',
  getPropertyValue: (property: string) => (
    property.includes('width') ? '1024px'
      : property.includes('height') ? '768px'
        : '0px'
  ),
}) as unknown as CSSStyleDeclaration;
