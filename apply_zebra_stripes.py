"""
为UI应用斑马纹效果（交替行背景色）
方案：为HBoxLayout设置Spacing和ContentsMargins，通过控件属性实现斑马纹
"""
from PyQt5.QtWidgets import QLayout

def apply_zebra_stripes_to_layout(layout, row_counter):
    """递归查找布局中的HBoxLayout并应用斑马纹"""
    if not layout:
        return

    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        
        child_layout = item.layout()
        child_widget = item.widget()
        
        # 跳过分隔线
        if child_widget and child_widget.objectName().startswith('line'):
            continue
            
        # 如果是容器Widget（如帆配置的容器），递归处理其布局
        if child_widget and child_widget.layout():
            apply_zebra_stripes_to_layout(child_widget.layout(), row_counter)
            continue
        
        if child_layout:
            # 检查是否是水平布局（行）
            if child_layout.objectName().startswith('horizontal'):
                # 检查是否包含管理按钮（增加、删除、更新），如果是则跳过（保持原有间隔）
                has_manage_buttons = False
                for j in range(child_layout.count()):
                    child_item = child_layout.itemAt(j)
                    if child_item and child_item.widget():
                        w_name = child_item.widget().objectName()
                        if any(x in w_name for x in ["AddPushButton", "Delete", "Update", "UpData"]):
                            has_manage_buttons = True
                            break
                
                if has_manage_buttons:
                    # 强制设置管理按钮行的间距为30
                    child_layout.setSpacing(30)
                    continue

                row_type = "even" if row_counter[0] % 2 == 0 else "odd"
                
                # 设置布局间距为0，让控件背景连成一片
                # 特殊处理帆类型选择，保留间距
                if child_layout.objectName() == "horizontalLayout_SailType":
                    child_layout.setSpacing(20)
                else:
                    child_layout.setSpacing(0)
                    
                child_layout.setContentsMargins(0, 0, 0, 0)
                # 为布局中的每个控件设置属性
                for j in range(child_layout.count()):
                    child_item = child_layout.itemAt(j)
                    if child_item:
                        widget = child_item.widget()
                        if widget:
                            widget.setProperty("row", row_type)
                            # 强制更新样式
                            widget.style().unpolish(widget)
                            widget.style().polish(widget)
                row_counter[0] += 1
            else:
                # 递归处理嵌套布局（如垂直布局）
                apply_zebra_stripes_to_layout(child_layout, row_counter)

def apply_zebra_stripes_to_groupbox(groupbox):
    """为GroupBox内的所有行应用交替背景色"""
    layout = groupbox.layout()
    if layout:
        row_counter = [0] # 使用列表作为可变引用
        apply_zebra_stripes_to_layout(layout, row_counter)

def apply_zebra_stripes(ui):
    """为所有页面应用斑马纹效果"""
    # 气球页
    if hasattr(ui, 'groupBox_SphereGeometry'):
        apply_zebra_stripes_to_groupbox(ui.groupBox_SphereGeometry)
    if hasattr(ui, 'groupBox_SphereMaterial'):
        apply_zebra_stripes_to_groupbox(ui.groupBox_SphereMaterial)
    if hasattr(ui, 'groupBox_SphereLoad'):
        apply_zebra_stripes_to_groupbox(ui.groupBox_SphereLoad)
    if hasattr(ui, 'groupBox_SphereCable'):
        apply_zebra_stripes_to_groupbox(ui.groupBox_SphereCable)
    
    # 飞艇页
    if hasattr(ui, 'groupBox_AirShipGeometry'):
        apply_zebra_stripes_to_groupbox(ui.groupBox_AirShipGeometry)
    if hasattr(ui, 'groupBox_AirShipMaterial'):
        apply_zebra_stripes_to_groupbox(ui.groupBox_AirShipMaterial)
    if hasattr(ui, 'groupBox_AirShipLoad'):
        apply_zebra_stripes_to_groupbox(ui.groupBox_AirShipLoad)
    if hasattr(ui, 'groupBox_AirShipCable'):
        apply_zebra_stripes_to_groupbox(ui.groupBox_AirShipCable)
    for prefix in ("Sphere", "AirShip"):
        for suffix in ("Result1", "Result2", "Result3"):
            group = getattr(ui, f"groupBox_{prefix}{suffix}", None)
            if group is not None:
                apply_zebra_stripes_to_groupbox(group)
    
    # 风压页
    if hasattr(ui, 'groupBox_4'):  # 风压查询
        apply_zebra_stripes_to_groupbox(ui.groupBox_4)
    if hasattr(ui, 'groupBox_6'):  # 风压数据库
        apply_zebra_stripes_to_groupbox(ui.groupBox_6)
    
    # 膜材页
    if hasattr(ui, 'groupBox_9'):  # 膜材查询
        apply_zebra_stripes_to_groupbox(ui.groupBox_9)
    if hasattr(ui, 'groupBox'):  # 膜材数据库
        apply_zebra_stripes_to_groupbox(ui.groupBox)
    
    # 缆绳页
    if hasattr(ui, 'groupBox_5'):  # 缆绳查询
        apply_zebra_stripes_to_groupbox(ui.groupBox_5)
    if hasattr(ui, 'groupBox_2'):  # 缆绳数据库
        apply_zebra_stripes_to_groupbox(ui.groupBox_2)
    
    # 管材页
    if hasattr(ui, 'groupBox_8'):  # 管材查询
        apply_zebra_stripes_to_groupbox(ui.groupBox_8)
    if hasattr(ui, 'groupBox_3'):  # 管材数据库
        apply_zebra_stripes_to_groupbox(ui.groupBox_3)

if __name__ == '__main__':
    print("此模块用于为UI应用斑马纹效果")
